//! Native Rust parser for `.rac` files (deployed DSL format).
//!
//! Ports TheAxiomFoundation/rac's Python recursive-descent parser. The surface
//! grammar matches the deployed engine so programmes authored for `rac-uk` /
//! `rac-us` load unchanged.
//!
//! ```text
//! module      = (entity | definition | amend)*
//! definition  = (PATH | NAME) ":" metadata* temporal+
//! temporal    = "from" DATE [to DATE] ":" expr
//! expr        = match | cond | or_expr
//! ```
//!
//! After parsing, [`Module::to_program`] lowers the rac AST into the engine's
//! [`crate::model::Program`]. Variables with no entity and a single literal
//! value lower to parameters; variables with an entity lower to derived
//! outputs; richer mappings handle match/cond/call/field access.

use std::collections::{BTreeMap, HashSet};
use std::path::Path;

use chrono::NaiveDate;
use rust_decimal::Decimal;
use std::str::FromStr;
use thiserror::Error;

use crate::model::{
    ComparisonOp, DType, Derived, DerivedSemantics, IndexedParameter, JudgmentExpr,
    ParameterVersion, Program, RelatedValueRef, ScalarExpr, ScalarValue, UnitDef, UnitKind,
};

#[derive(Debug, Error)]
pub enum RacError {
    #[error("rac parse error at line {line}, col {col}: {message}")]
    Parse {
        line: usize,
        col: usize,
        message: String,
    },
    #[error("rac lower error: {0}")]
    Lower(String),
    #[error("failed to read .rac file `{path}`: {error}")]
    Io {
        path: String,
        error: std::io::Error,
    },
}

impl RacError {
    fn parse<S: Into<String>>(line: usize, col: usize, message: S) -> Self {
        RacError::Parse {
            line,
            col,
            message: message.into(),
        }
    }
    fn lower<S: Into<String>>(msg: S) -> Self {
        RacError::Lower(msg.into())
    }
}

// ---------------------------------------------------------------------------
// Lexer
// ---------------------------------------------------------------------------

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum TokType {
    Ident,
    Path,
    Int,
    Float,
    String,
    Date,
    // Keywords
    Entity,
    Amend,
    From,
    To,
    Match,
    If,
    Elif,
    Else,
    And,
    Or,
    Not,
    True,
    False,
    // Punctuation / operators
    Colon,
    Comma,
    Dot,
    Arrow,   // =>
    Fk,      // ->
    Assign,  // =
    Le, Ge, Eq, Ne,
    Lt, Gt,
    Plus, Minus, Star, Slash,
    LParen, RParen, LBracket, RBracket,
    Eof,
}

#[derive(Clone, Debug)]
pub struct Token {
    pub ty: TokType,
    pub value: String,
    pub line: usize,
    pub col: usize,
}

fn keyword(s: &str) -> Option<TokType> {
    match s {
        "entity" => Some(TokType::Entity),
        "amend" => Some(TokType::Amend),
        "from" => Some(TokType::From),
        "to" => Some(TokType::To),
        "match" => Some(TokType::Match),
        "if" => Some(TokType::If),
        "elif" => Some(TokType::Elif),
        "else" => Some(TokType::Else),
        "and" => Some(TokType::And),
        "or" => Some(TokType::Or),
        "not" => Some(TokType::Not),
        "true" | "True" => Some(TokType::True),
        "false" | "False" => Some(TokType::False),
        _ => None,
    }
}

pub struct Lexer<'a> {
    src: &'a [u8],
    pos: usize,
    line: usize,
    col: usize,
    tokens: Vec<Token>,
}

impl<'a> Lexer<'a> {
    pub fn new(src: &'a str) -> Self {
        Self {
            src: src.as_bytes(),
            pos: 0,
            line: 1,
            col: 1,
            tokens: Vec::new(),
        }
    }

    fn peek(&self, offset: usize) -> Option<u8> {
        self.src.get(self.pos + offset).copied()
    }

    fn advance(&mut self, n: usize) {
        for _ in 0..n {
            if self.pos >= self.src.len() {
                break;
            }
            let c = self.src[self.pos];
            self.pos += 1;
            if c == b'\n' {
                self.line += 1;
                self.col = 1;
            } else {
                self.col += 1;
            }
        }
    }

    fn push(&mut self, ty: TokType, value: String, line: usize, col: usize) {
        self.tokens.push(Token { ty, value, line, col });
    }

    pub fn tokenise(mut self) -> Result<Vec<Token>, RacError> {
        while self.pos < self.src.len() {
            // Triple-quoted block (statute docstring). Skip without emitting.
            if self.pos + 3 <= self.src.len() && &self.src[self.pos..self.pos + 3] == b"\"\"\"" {
                let start = self.pos + 3;
                if let Some(rel) = find_bytes(&self.src[start..], b"\"\"\"") {
                    self.advance(rel + 6);
                } else {
                    self.advance(self.src.len() - self.pos);
                }
                continue;
            }

            // Comment
            if self.src[self.pos] == b'#' {
                while self.pos < self.src.len() && self.src[self.pos] != b'\n' {
                    self.advance(1);
                }
                continue;
            }

            // Whitespace
            if self.src[self.pos].is_ascii_whitespace() {
                self.advance(1);
                continue;
            }

            let line = self.line;
            let col = self.col;
            let c = self.src[self.pos];

            // Date: YYYY-MM-DD
            if c.is_ascii_digit() && self.pos + 10 <= self.src.len() {
                let slice = &self.src[self.pos..self.pos + 10];
                if slice[4] == b'-' && slice[7] == b'-'
                    && slice.iter().enumerate().all(|(i, &b)| {
                        matches!(i, 4 | 7) || b.is_ascii_digit()
                    })
                {
                    let s = std::str::from_utf8(slice).unwrap().to_string();
                    self.advance(10);
                    self.push(TokType::Date, s, line, col);
                    continue;
                }
            }

            // Number (int or float). Allows underscores.
            if c.is_ascii_digit() {
                let mut end = self.pos;
                while end < self.src.len()
                    && (self.src[end].is_ascii_digit() || self.src[end] == b'_')
                {
                    end += 1;
                }
                let mut is_float = false;
                if end < self.src.len() && self.src[end] == b'.' {
                    // Lookahead: next must be digit
                    if end + 1 < self.src.len() && self.src[end + 1].is_ascii_digit() {
                        is_float = true;
                        end += 1;
                        while end < self.src.len()
                            && (self.src[end].is_ascii_digit() || self.src[end] == b'_')
                        {
                            end += 1;
                        }
                    }
                }
                let s = std::str::from_utf8(&self.src[self.pos..end]).unwrap().to_string();
                let n = end - self.pos;
                self.advance(n);
                self.push(
                    if is_float { TokType::Float } else { TokType::Int },
                    s,
                    line,
                    col,
                );
                continue;
            }

            // String literal
            if c == b'"' || c == b'\'' {
                let quote = c;
                let start = self.pos + 1;
                let mut end = start;
                while end < self.src.len() && self.src[end] != quote {
                    end += 1;
                }
                if end >= self.src.len() {
                    return Err(RacError::parse(line, col, "unterminated string"));
                }
                let s = std::str::from_utf8(&self.src[start..end]).unwrap().to_string();
                let n = end + 1 - self.pos;
                self.advance(n);
                self.push(TokType::String, s, line, col);
                continue;
            }

            // Identifier / path / keyword
            if c.is_ascii_alphabetic() || c == b'_' {
                let mut end = self.pos;
                while end < self.src.len()
                    && (self.src[end].is_ascii_alphanumeric() || self.src[end] == b'_')
                {
                    end += 1;
                }
                // Path: IDENT (/ IDENT)+
                let mut is_path = false;
                let mut path_end = end;
                while path_end < self.src.len() && self.src[path_end] == b'/' {
                    let next_start = path_end + 1;
                    if next_start < self.src.len()
                        && (self.src[next_start].is_ascii_alphabetic() || self.src[next_start] == b'_')
                    {
                        is_path = true;
                        let mut q = next_start + 1;
                        while q < self.src.len()
                            && (self.src[q].is_ascii_alphanumeric() || self.src[q] == b'_')
                        {
                            q += 1;
                        }
                        path_end = q;
                    } else {
                        break;
                    }
                }
                let final_end = if is_path { path_end } else { end };
                let s = std::str::from_utf8(&self.src[self.pos..final_end]).unwrap().to_string();
                let n = final_end - self.pos;
                self.advance(n);
                if !is_path {
                    if let Some(kw) = keyword(&s) {
                        self.push(kw, s, line, col);
                    } else {
                        self.push(TokType::Ident, s, line, col);
                    }
                } else {
                    self.push(TokType::Path, s, line, col);
                }
                continue;
            }

            // Multi-char operators
            if self.pos + 2 <= self.src.len() {
                let pair = &self.src[self.pos..self.pos + 2];
                let ty = match pair {
                    b"=>" => Some(TokType::Arrow),
                    b"<=" => Some(TokType::Le),
                    b">=" => Some(TokType::Ge),
                    b"==" => Some(TokType::Eq),
                    b"!=" => Some(TokType::Ne),
                    b"->" => Some(TokType::Fk),
                    _ => None,
                };
                if let Some(ty) = ty {
                    let s = std::str::from_utf8(pair).unwrap().to_string();
                    self.advance(2);
                    self.push(ty, s, line, col);
                    continue;
                }
            }

            // Single-char operators
            let (ty, len) = match c {
                b':' => (TokType::Colon, 1),
                b',' => (TokType::Comma, 1),
                b'.' => (TokType::Dot, 1),
                b'=' => (TokType::Assign, 1),
                b'+' => (TokType::Plus, 1),
                b'-' => (TokType::Minus, 1),
                b'*' => (TokType::Star, 1),
                b'/' => (TokType::Slash, 1),
                b'<' => (TokType::Lt, 1),
                b'>' => (TokType::Gt, 1),
                b'(' => (TokType::LParen, 1),
                b')' => (TokType::RParen, 1),
                b'[' => (TokType::LBracket, 1),
                b']' => (TokType::RBracket, 1),
                _ => {
                    return Err(RacError::parse(
                        line,
                        col,
                        format!("unexpected char {:?}", c as char),
                    ));
                }
            };
            let s = (c as char).to_string();
            self.advance(len);
            self.push(ty, s, line, col);
        }

        self.push(TokType::Eof, String::new(), self.line, self.col);
        Ok(self.tokens)
    }
}

fn find_bytes(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|w| w == needle)
}

// ---------------------------------------------------------------------------
// AST
// ---------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub enum Expr {
    LitInt(i64),
    LitFloat(Decimal),
    LitStr(String),
    LitBool(bool),
    Var(String),
    BinOp { op: BinOpKind, left: Box<Expr>, right: Box<Expr> },
    UnaryOp { op: UnaryOpKind, operand: Box<Expr> },
    Call { func: String, args: Vec<Expr> },
    FieldAccess { obj: Box<Expr>, field: String },
    Cond { condition: Box<Expr>, then_expr: Box<Expr>, else_expr: Box<Expr> },
    Match { subject: Box<Expr>, cases: Vec<(Expr, Expr)> },
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BinOpKind {
    Add, Sub, Mul, Div,
    Lt, Gt, Le, Ge, Eq, Ne,
    And, Or,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum UnaryOpKind { Neg, Not }

#[derive(Clone, Debug)]
pub struct TemporalValue {
    pub start: NaiveDate,
    pub end: Option<NaiveDate>,
    pub expr: Expr,
}

#[derive(Clone, Debug, Default)]
pub struct VariableDecl {
    pub path: String,
    pub entity: Option<String>,
    pub dtype: Option<String>,
    pub period: Option<String>,
    pub unit: Option<String>,
    pub source: Option<String>,
    pub source_url: Option<String>,
    pub label: Option<String>,
    pub description: Option<String>,
    pub default: Option<String>,
    pub indexed_by: Option<String>,
    pub values: Vec<TemporalValue>,
}

#[derive(Clone, Debug, Default)]
pub struct Module {
    pub variables: Vec<VariableDecl>,
}

// ---------------------------------------------------------------------------
// Parser
// ---------------------------------------------------------------------------

const METADATA_FIELDS: &[&str] = &[
    "source", "source_url", "label", "description", "unit", "dtype",
    "period", "default", "indexed_by", "status",
];

pub struct Parser {
    tokens: Vec<Token>,
    pos: usize,
}

impl Parser {
    pub fn new(tokens: Vec<Token>) -> Self {
        Self { tokens, pos: 0 }
    }

    fn peek(&self, offset: usize) -> &Token {
        let idx = (self.pos + offset).min(self.tokens.len() - 1);
        &self.tokens[idx]
    }

    fn at(&self, tys: &[TokType]) -> bool {
        tys.iter().any(|t| self.peek(0).ty == *t)
    }

    fn consume(&mut self, ty: TokType) -> Result<Token, RacError> {
        let tok = self.peek(0).clone();
        if tok.ty != ty {
            return Err(RacError::parse(
                tok.line,
                tok.col,
                format!("expected {:?}, got {:?} ({})", ty, tok.ty, tok.value),
            ));
        }
        self.pos += 1;
        Ok(tok)
    }

    fn match_one(&mut self, tys: &[TokType]) -> Option<Token> {
        if self.at(tys) {
            let tok = self.peek(0).clone();
            self.pos += 1;
            Some(tok)
        } else {
            None
        }
    }

    pub fn parse_module(&mut self) -> Result<Module, RacError> {
        let mut module = Module::default();
        while self.peek(0).ty != TokType::Eof {
            if self.at(&[TokType::Entity]) {
                // Skip entity declarations entirely — engine infers entities from data.
                self.skip_entity()?;
                continue;
            }
            if self.at(&[TokType::Amend]) {
                // Amendments not used by our test corpus yet; skip.
                self.skip_amend()?;
                continue;
            }
            if self.at(&[TokType::Ident, TokType::Path])
                && self.peek(1).ty == TokType::Colon
            {
                // Skip bare metadata lines like `status: boilerplate` with no body
                if self.peek(0).ty == TokType::Ident
                    && self.peek(0).value == "status"
                    && matches!(self.peek(2).ty, TokType::Ident | TokType::String)
                    && self.peek(3).ty != TokType::Colon
                {
                    self.pos += 3;
                    continue;
                }
                module.variables.push(self.parse_variable()?);
                continue;
            }
            let tok = self.peek(0).clone();
            return Err(RacError::parse(
                tok.line,
                tok.col,
                format!("unexpected token {:?} ({})", tok.ty, tok.value),
            ));
        }
        Ok(module)
    }

    fn skip_entity(&mut self) -> Result<(), RacError> {
        self.consume(TokType::Entity)?;
        self.consume(TokType::Ident)?;
        self.consume(TokType::Colon)?;
        // Skip fields while we see `ident: ...`
        while self.peek(0).ty == TokType::Ident && self.peek(1).ty == TokType::Colon {
            // Lookahead: does this look like a variable declaration rather
            // than an entity field? A variable decl has a metadata line or
            // a `from` block after. Entity fields have a single type token.
            // Simplest heuristic: if the token after the colon is a
            // single IDENT followed by another `ident:` pair (next field)
            // or EOF/ENTITY/AMEND, treat as a field.
            let after_colon = self.peek(2).ty.clone();
            if !matches!(after_colon, TokType::Ident | TokType::LBracket | TokType::Fk) {
                break;
            }
            self.consume(TokType::Ident)?; // field name
            self.consume(TokType::Colon)?;
            if self.at(&[TokType::Fk]) {
                self.consume(TokType::Fk)?;
                self.consume(TokType::Ident)?;
            } else if self.at(&[TokType::LBracket]) {
                self.consume(TokType::LBracket)?;
                self.consume(TokType::Ident)?;
                self.consume(TokType::RBracket)?;
            } else {
                self.consume(TokType::Ident)?; // type name
            }
        }
        Ok(())
    }

    fn skip_amend(&mut self) -> Result<(), RacError> {
        self.consume(TokType::Amend)?;
        // Target path
        if self.at(&[TokType::Path]) {
            self.consume(TokType::Path)?;
        } else {
            self.consume(TokType::Ident)?;
        }
        self.consume(TokType::Colon)?;
        // Skip temporal values
        while self.at(&[TokType::From]) {
            self.consume(TokType::From)?;
            self.consume(TokType::Date)?;
            if self.at(&[TokType::To]) {
                self.consume(TokType::To)?;
                self.consume(TokType::Date)?;
            }
            self.consume(TokType::Colon)?;
            self.parse_expr()?;
        }
        Ok(())
    }

    fn parse_variable(&mut self) -> Result<VariableDecl, RacError> {
        let path = self.parse_path()?;
        self.consume(TokType::Colon)?;
        let mut decl = VariableDecl {
            path,
            ..Default::default()
        };
        // Metadata + optional entity, any order
        loop {
            if self.at(&[TokType::Entity]) {
                self.consume(TokType::Entity)?;
                self.consume(TokType::Colon)?;
                let t = self.consume(TokType::Ident)?;
                decl.entity = Some(t.value);
                continue;
            }
            if self.peek(0).ty == TokType::Ident
                && self.peek(1).ty == TokType::Colon
                && METADATA_FIELDS.contains(&self.peek(0).value.as_str())
            {
                let field = self.consume(TokType::Ident)?.value;
                self.consume(TokType::Colon)?;
                let tok = self.peek(0).clone();
                let v = match tok.ty {
                    TokType::String => self.consume(TokType::String)?.value,
                    TokType::Ident | TokType::Int | TokType::Float => {
                        let mut val = self.consume(tok.ty.clone())?.value;
                        // Skip type-suffix brackets e.g. `Enum[Status]`
                        if self.at(&[TokType::LBracket]) {
                            self.consume(TokType::LBracket)?;
                            let mut depth = 1;
                            while depth > 0 && self.peek(0).ty != TokType::Eof {
                                match self.peek(0).ty {
                                    TokType::LBracket => depth += 1,
                                    TokType::RBracket => depth -= 1,
                                    _ => {}
                                }
                                self.pos += 1;
                            }
                        }
                        // Handle unit with path-like value (e.g. `unit: GBP/week`)
                        // already a Path token; handled above as Ident branch won't fire
                        let _ = &mut val;
                        val
                    }
                    TokType::Path => self.consume(TokType::Path)?.value,
                    TokType::Minus => {
                        self.consume(TokType::Minus)?;
                        let t = self.peek(0).ty.clone();
                        let v = self.consume(t)?.value;
                        format!("-{v}")
                    }
                    TokType::True => {
                        self.consume(TokType::True)?;
                        "true".to_string()
                    }
                    TokType::False => {
                        self.consume(TokType::False)?;
                        "false".to_string()
                    }
                    _ => {
                        return Err(RacError::parse(
                            tok.line,
                            tok.col,
                            format!("unexpected metadata value {:?}", tok.ty),
                        ));
                    }
                };
                match field.as_str() {
                    "source" => decl.source = Some(v),
                    "source_url" => decl.source_url = Some(v),
                    "label" => decl.label = Some(v),
                    "description" => decl.description = Some(v),
                    "unit" => decl.unit = Some(v),
                    "dtype" => decl.dtype = Some(v),
                    "period" => decl.period = Some(v),
                    "default" => decl.default = Some(v),
                    "indexed_by" => decl.indexed_by = Some(v),
                    "status" => {}
                    _ => {}
                }
                continue;
            }
            break;
        }
        // Temporal values: at least one `from DATE [to DATE]: expr`
        while self.at(&[TokType::From]) {
            self.consume(TokType::From)?;
            let start_tok = self.consume(TokType::Date)?;
            let start = NaiveDate::parse_from_str(&start_tok.value, "%Y-%m-%d")
                .map_err(|e| RacError::parse(start_tok.line, start_tok.col, e.to_string()))?;
            let mut end = None;
            if self.at(&[TokType::To]) {
                self.consume(TokType::To)?;
                let t = self.consume(TokType::Date)?;
                end = Some(
                    NaiveDate::parse_from_str(&t.value, "%Y-%m-%d")
                        .map_err(|e| RacError::parse(t.line, t.col, e.to_string()))?,
                );
            }
            self.consume(TokType::Colon)?;
            let expr = self.parse_expr()?;
            decl.values.push(TemporalValue { start, end, expr });
        }
        Ok(decl)
    }

    fn parse_path(&mut self) -> Result<String, RacError> {
        if self.at(&[TokType::Path]) {
            Ok(self.consume(TokType::Path)?.value)
        } else {
            Ok(self.consume(TokType::Ident)?.value)
        }
    }

    fn parse_expr(&mut self) -> Result<Expr, RacError> {
        // Let-bindings: IDENT ASSIGN value body
        if self.peek(0).ty == TokType::Ident && self.peek(1).ty == TokType::Assign {
            // Let-bindings aren't lowered by our engine yet. Inline the value
            // at the use site manually; until then, this is an error if hit.
            let tok = self.peek(0).clone();
            return Err(RacError::parse(
                tok.line,
                tok.col,
                "let-bindings are not supported in the Rust .rac loader yet".to_string(),
            ));
        }
        if self.at(&[TokType::Match]) {
            return self.parse_match();
        }
        if self.at(&[TokType::If]) {
            return self.parse_cond();
        }
        self.parse_or()
    }

    fn parse_match(&mut self) -> Result<Expr, RacError> {
        self.consume(TokType::Match)?;
        let subject = self.parse_or()?;
        self.consume(TokType::Colon)?;
        let mut cases = Vec::new();
        while matches!(
            self.peek(0).ty,
            TokType::Int
                | TokType::Float
                | TokType::String
                | TokType::True
                | TokType::False
                | TokType::Ident
        ) && self.peek(1).ty == TokType::Arrow
        {
            let pat = self.parse_primary()?;
            self.consume(TokType::Arrow)?;
            let res = self.parse_expr()?;
            cases.push((pat, res));
        }
        Ok(Expr::Match { subject: Box::new(subject), cases })
    }

    fn parse_cond(&mut self) -> Result<Expr, RacError> {
        self.consume(TokType::If)?;
        let cond = self.parse_or()?;
        self.consume(TokType::Colon)?;
        let then_expr = self.parse_expr()?;
        let else_expr = if self.match_one(&[TokType::Elif]).is_some() {
            let elif_cond = self.parse_or()?;
            self.consume(TokType::Colon)?;
            let elif_then = self.parse_expr()?;
            self.parse_elif_chain(elif_cond, elif_then)?
        } else {
            self.consume(TokType::Else)?;
            self.consume(TokType::Colon)?;
            self.parse_expr()?
        };
        Ok(Expr::Cond {
            condition: Box::new(cond),
            then_expr: Box::new(then_expr),
            else_expr: Box::new(else_expr),
        })
    }

    fn parse_elif_chain(&mut self, cond: Expr, then_expr: Expr) -> Result<Expr, RacError> {
        let else_expr = if self.match_one(&[TokType::Elif]).is_some() {
            let next_cond = self.parse_or()?;
            self.consume(TokType::Colon)?;
            let next_then = self.parse_expr()?;
            self.parse_elif_chain(next_cond, next_then)?
        } else {
            self.consume(TokType::Else)?;
            self.consume(TokType::Colon)?;
            self.parse_expr()?
        };
        Ok(Expr::Cond {
            condition: Box::new(cond),
            then_expr: Box::new(then_expr),
            else_expr: Box::new(else_expr),
        })
    }

    fn parse_or(&mut self) -> Result<Expr, RacError> {
        let mut left = self.parse_and()?;
        while self.match_one(&[TokType::Or]).is_some() {
            let right = self.parse_and()?;
            left = Expr::BinOp { op: BinOpKind::Or, left: Box::new(left), right: Box::new(right) };
        }
        Ok(left)
    }

    fn parse_and(&mut self) -> Result<Expr, RacError> {
        let mut left = self.parse_cmp()?;
        while self.match_one(&[TokType::And]).is_some() {
            let right = self.parse_cmp()?;
            left = Expr::BinOp { op: BinOpKind::And, left: Box::new(left), right: Box::new(right) };
        }
        Ok(left)
    }

    fn parse_cmp(&mut self) -> Result<Expr, RacError> {
        let left = self.parse_add()?;
        let op = match self.peek(0).ty {
            TokType::Lt => Some(BinOpKind::Lt),
            TokType::Gt => Some(BinOpKind::Gt),
            TokType::Le => Some(BinOpKind::Le),
            TokType::Ge => Some(BinOpKind::Ge),
            TokType::Eq => Some(BinOpKind::Eq),
            TokType::Ne => Some(BinOpKind::Ne),
            _ => None,
        };
        if let Some(op) = op {
            self.pos += 1;
            let right = self.parse_add()?;
            return Ok(Expr::BinOp { op, left: Box::new(left), right: Box::new(right) });
        }
        Ok(left)
    }

    fn parse_add(&mut self) -> Result<Expr, RacError> {
        let mut left = self.parse_mul()?;
        loop {
            let op = match self.peek(0).ty {
                TokType::Plus => BinOpKind::Add,
                TokType::Minus => BinOpKind::Sub,
                _ => break,
            };
            self.pos += 1;
            let right = self.parse_mul()?;
            left = Expr::BinOp { op, left: Box::new(left), right: Box::new(right) };
        }
        Ok(left)
    }

    fn parse_mul(&mut self) -> Result<Expr, RacError> {
        let mut left = self.parse_unary()?;
        loop {
            let op = match self.peek(0).ty {
                TokType::Star => BinOpKind::Mul,
                TokType::Slash => BinOpKind::Div,
                _ => break,
            };
            self.pos += 1;
            let right = self.parse_unary()?;
            left = Expr::BinOp { op, left: Box::new(left), right: Box::new(right) };
        }
        Ok(left)
    }

    fn parse_unary(&mut self) -> Result<Expr, RacError> {
        if self.match_one(&[TokType::Minus]).is_some() {
            let operand = self.parse_unary()?;
            return Ok(Expr::UnaryOp { op: UnaryOpKind::Neg, operand: Box::new(operand) });
        }
        if self.match_one(&[TokType::Not]).is_some() {
            let operand = self.parse_unary()?;
            return Ok(Expr::UnaryOp { op: UnaryOpKind::Not, operand: Box::new(operand) });
        }
        self.parse_postfix()
    }

    fn parse_postfix(&mut self) -> Result<Expr, RacError> {
        let mut expr = self.parse_primary()?;
        loop {
            if self.at(&[TokType::LParen]) {
                // Call — expr must be a Var
                let func = match &expr {
                    Expr::Var(name) => name.clone(),
                    _ => {
                        let tok = self.peek(0).clone();
                        return Err(RacError::parse(
                            tok.line,
                            tok.col,
                            "can only call named functions".to_string(),
                        ));
                    }
                };
                self.consume(TokType::LParen)?;
                let mut args = Vec::new();
                if !self.at(&[TokType::RParen]) {
                    args.push(self.parse_expr()?);
                    while self.match_one(&[TokType::Comma]).is_some() {
                        args.push(self.parse_expr()?);
                    }
                }
                self.consume(TokType::RParen)?;
                expr = Expr::Call { func, args };
            } else if self.at(&[TokType::Dot]) {
                self.consume(TokType::Dot)?;
                let field = self.consume(TokType::Ident)?.value;
                expr = Expr::FieldAccess { obj: Box::new(expr), field };
            } else {
                break;
            }
        }
        Ok(expr)
    }

    fn parse_primary(&mut self) -> Result<Expr, RacError> {
        let tok = self.peek(0).clone();
        match tok.ty {
            TokType::Int => {
                self.pos += 1;
                let v: i64 = tok
                    .value
                    .replace('_', "")
                    .parse()
                    .map_err(|e: std::num::ParseIntError| {
                        RacError::parse(tok.line, tok.col, e.to_string())
                    })?;
                Ok(Expr::LitInt(v))
            }
            TokType::Float => {
                self.pos += 1;
                let v = Decimal::from_str(&tok.value.replace('_', "")).map_err(|e| {
                    RacError::parse(tok.line, tok.col, e.to_string())
                })?;
                Ok(Expr::LitFloat(v))
            }
            TokType::String => {
                self.pos += 1;
                Ok(Expr::LitStr(tok.value))
            }
            TokType::True => {
                self.pos += 1;
                Ok(Expr::LitBool(true))
            }
            TokType::False => {
                self.pos += 1;
                Ok(Expr::LitBool(false))
            }
            TokType::Ident | TokType::Path => {
                self.pos += 1;
                Ok(Expr::Var(tok.value))
            }
            TokType::LParen => {
                self.consume(TokType::LParen)?;
                let e = self.parse_expr()?;
                self.consume(TokType::RParen)?;
                Ok(e)
            }
            _ => Err(RacError::parse(
                tok.line,
                tok.col,
                format!("unexpected token in expression: {:?} ({})", tok.ty, tok.value),
            )),
        }
    }
}

pub fn parse_source(src: &str) -> Result<Module, RacError> {
    let tokens = Lexer::new(src).tokenise()?;
    let mut parser = Parser::new(tokens);
    parser.parse_module()
}

pub fn parse_file<P: AsRef<Path>>(path: P) -> Result<Module, RacError> {
    let path = path.as_ref();
    let src = std::fs::read_to_string(path).map_err(|e| RacError::Io {
        path: path.display().to_string(),
        error: e,
    })?;
    parse_source(&src)
}

// ---------------------------------------------------------------------------
// Lowering to engine's Program model
// ---------------------------------------------------------------------------

/// Lower a parsed `.rac` `Module` into the engine's `Program`.
///
/// Convention for now:
/// - A `VariableDecl` with no `entity` whose single temporal value is a
///   literal lowers to a scalar `Parameter` keyed at index 0 (or at integer
///   keys if the literal is an integer-keyed table once indexed_by support
///   lands).
/// - A `VariableDecl` with an `entity` lowers to a `Derived` output. Its
///   expression is the expression from the currently-effective temporal
///   value (picked by the caller's query period at execution time — for
///   now we take the latest one).
/// - Non-literal scalar variables (with no entity but a computed expression)
///   lower to derived outputs attached to a synthetic `Scalar` entity so
///   they can be referenced from entity-scoped derived values.
pub fn lower_module(module: &Module) -> Result<Program, RacError> {
    let mut program = Program::default();

    // Helpful unit defaults so programmes don't have to re-declare common
    // units. The engine's `UnitKind` distinguishes currency / count / ratio /
    // custom; missing unit declarations would otherwise reject YAML-era
    // programmes that relied on them via ProgramSpec.
    for (name, kind) in [
        ("GBP", UnitKind::Currency { minor_units: 2 }),
        ("USD", UnitKind::Currency { minor_units: 2 }),
        ("EUR", UnitKind::Currency { minor_units: 2 }),
        ("count", UnitKind::Count),
        ("person", UnitKind::Count),
        ("ratio", UnitKind::Ratio),
        ("status", UnitKind::Custom("judgment".to_string())),
    ] {
        program.add_unit(UnitDef {
            name: name.to_string(),
            kind,
        });
    }

    // Collect names of no-entity, literal-only variables so other variables
    // can reference them as scalar parameters rather than mis-interpreting
    // them as entity inputs.
    let mut scalar_names: HashSet<String> = HashSet::new();
    let mut derived_names: HashSet<String> = HashSet::new();
    for v in &module.variables {
        if v.entity.is_some() {
            derived_names.insert(v.path.clone());
        } else if v.values.iter().all(|t| is_literal_expr(&t.expr)) {
            scalar_names.insert(v.path.clone());
        } else {
            // computed scalar — treat as derived against a synthetic entity
            derived_names.insert(v.path.clone());
        }
    }

    // First pass: scalar parameters.
    for v in &module.variables {
        if v.entity.is_some() {
            continue;
        }
        if !v.values.iter().all(|t| is_literal_expr(&t.expr)) {
            continue;
        }
        let mut versions: Vec<ParameterVersion> = Vec::new();
        for t in &v.values {
            let mut values: BTreeMap<i64, ScalarValue> = BTreeMap::new();
            values.insert(0, literal_to_scalar_value(&t.expr)?);
            versions.push(ParameterVersion {
                effective_from: t.start,
                values,
            });
        }
        let param = IndexedParameter {
            name: v.path.clone(),
            unit: v.unit.clone(),
            versions,
        };
        program.add_parameter(param);
    }

    // Second pass: derived outputs. Pick the latest temporal value's expr.
    let ctx = LowerCtx {
        scalars: scalar_names,
        derived: derived_names,
    };
    for v in &module.variables {
        if v.entity.is_none() {
            // Non-literal no-entity variables: treat as scalar-scope derived.
            if v.values.iter().all(|t| is_literal_expr(&t.expr)) {
                continue;
            }
        }
        let dtype = parse_dtype(v.dtype.as_deref());
        let entity = v.entity.clone().unwrap_or_else(|| "Scalar".to_string());
        let last = v.values.last().ok_or_else(|| {
            RacError::lower(format!("variable `{}` has no temporal values", v.path))
        })?;
        let (semantics, _) = match dtype {
            DType::Judgment => {
                let expr = lower_to_judgment(&last.expr, &ctx)?;
                (DerivedSemantics::Judgment(expr), ())
            }
            _ => {
                let expr = lower_to_scalar(&last.expr, &ctx)?;
                (DerivedSemantics::Scalar(expr), ())
            }
        };
        program.add_derived(Derived {
            name: v.path.clone(),
            entity,
            dtype,
            unit: v.unit.clone(),
            source: v.source.clone(),
            source_url: v.source_url.clone(),
            semantics,
        });
    }

    Ok(program)
}

fn is_literal_expr(e: &Expr) -> bool {
    matches!(
        e,
        Expr::LitInt(_) | Expr::LitFloat(_) | Expr::LitBool(_) | Expr::LitStr(_)
    )
}

fn literal_to_scalar_value(e: &Expr) -> Result<ScalarValue, RacError> {
    match e {
        Expr::LitInt(i) => Ok(ScalarValue::Integer(*i)),
        Expr::LitFloat(d) => Ok(ScalarValue::Decimal(*d)),
        Expr::LitBool(b) => Ok(ScalarValue::Bool(*b)),
        Expr::LitStr(s) => Ok(ScalarValue::Text(s.clone())),
        _ => Err(RacError::lower("expected literal expression".to_string())),
    }
}

fn parse_dtype(s: Option<&str>) -> DType {
    match s {
        Some("Judgment") | Some("judgment") => DType::Judgment,
        Some("Boolean") | Some("Bool") | Some("boolean") | Some("bool") => DType::Bool,
        Some("Integer") | Some("integer") | Some("int") => DType::Integer,
        Some("Money") | Some("money") | Some("Rate") | Some("rate") | Some("Decimal")
        | Some("decimal") | Some("float") => DType::Decimal,
        Some("Text") | Some("text") | Some("String") | Some("string") => DType::Text,
        Some("Date") | Some("date") => DType::Date,
        _ => DType::Decimal,
    }
}

struct LowerCtx {
    scalars: HashSet<String>,
    derived: HashSet<String>,
}

fn lower_to_scalar(e: &Expr, ctx: &LowerCtx) -> Result<ScalarExpr, RacError> {
    Ok(match e {
        Expr::LitInt(i) => ScalarExpr::Literal(ScalarValue::Integer(*i)),
        Expr::LitFloat(d) => ScalarExpr::Literal(ScalarValue::Decimal(*d)),
        Expr::LitBool(b) => ScalarExpr::Literal(ScalarValue::Bool(*b)),
        Expr::LitStr(s) => ScalarExpr::Literal(ScalarValue::Text(s.clone())),
        Expr::Var(name) => {
            if ctx.scalars.contains(name) {
                ScalarExpr::ParameterLookup {
                    parameter: name.clone(),
                    index: Box::new(ScalarExpr::Literal(ScalarValue::Integer(0))),
                }
            } else if ctx.derived.contains(name) {
                ScalarExpr::Derived(name.clone())
            } else {
                ScalarExpr::Input(name.clone())
            }
        }
        Expr::BinOp { op, left, right } => {
            let l = lower_to_scalar(left, ctx)?;
            let r = lower_to_scalar(right, ctx)?;
            match op {
                BinOpKind::Add => ScalarExpr::Add(vec![l, r]),
                BinOpKind::Sub => ScalarExpr::Sub(Box::new(l), Box::new(r)),
                BinOpKind::Mul => ScalarExpr::Mul(Box::new(l), Box::new(r)),
                BinOpKind::Div => ScalarExpr::Div(Box::new(l), Box::new(r)),
                _ => {
                    return Err(RacError::lower(format!(
                        "binary op {:?} in scalar position",
                        op
                    )));
                }
            }
        }
        Expr::UnaryOp { op, operand } => match op {
            UnaryOpKind::Neg => ScalarExpr::Sub(
                Box::new(ScalarExpr::Literal(ScalarValue::Integer(0))),
                Box::new(lower_to_scalar(operand, ctx)?),
            ),
            UnaryOpKind::Not => {
                return Err(RacError::lower("`not` in scalar position".to_string()));
            }
        },
        Expr::Call { func, args } => match func.as_str() {
            "max" => ScalarExpr::Max(
                args.iter()
                    .map(|a| lower_to_scalar(a, ctx))
                    .collect::<Result<_, _>>()?,
            ),
            "min" => ScalarExpr::Min(
                args.iter()
                    .map(|a| lower_to_scalar(a, ctx))
                    .collect::<Result<_, _>>()?,
            ),
            "ceil" => {
                if args.len() != 1 {
                    return Err(RacError::lower("ceil takes 1 arg".to_string()));
                }
                ScalarExpr::Ceil(Box::new(lower_to_scalar(&args[0], ctx)?))
            }
            "floor" => {
                if args.len() != 1 {
                    return Err(RacError::lower("floor takes 1 arg".to_string()));
                }
                ScalarExpr::Floor(Box::new(lower_to_scalar(&args[0], ctx)?))
            }
            "days_between" => {
                if args.len() != 2 {
                    return Err(RacError::lower("days_between takes 2 args".to_string()));
                }
                ScalarExpr::DaysBetween {
                    from: Box::new(lower_to_scalar(&args[0], ctx)?),
                    to: Box::new(lower_to_scalar(&args[1], ctx)?),
                }
            }
            "date_add_days" => {
                if args.len() != 2 {
                    return Err(RacError::lower("date_add_days takes 2 args".to_string()));
                }
                ScalarExpr::DateAddDays {
                    date: Box::new(lower_to_scalar(&args[0], ctx)?),
                    days: Box::new(lower_to_scalar(&args[1], ctx)?),
                }
            }
            "len" => {
                // `len(members)` — count over a relation with no filter.
                if let Some(Expr::Var(rel)) = args.first() {
                    return Ok(ScalarExpr::CountRelated {
                        relation: rel.clone(),
                        current_slot: 1,
                        related_slot: 0,
                        where_clause: None,
                    });
                }
                if let Some(Expr::FieldAccess { obj, .. }) = args.first() {
                    if let Expr::Var(rel) = obj.as_ref() {
                        return Ok(ScalarExpr::CountRelated {
                            relation: rel.clone(),
                            current_slot: 1,
                            related_slot: 0,
                            where_clause: None,
                        });
                    }
                }
                return Err(RacError::lower(
                    "len(...) requires a relation argument".to_string(),
                ));
            }
            "sum" => {
                if let Some(Expr::FieldAccess { obj, field }) = args.first() {
                    if let Expr::Var(rel) = obj.as_ref() {
                        return Ok(ScalarExpr::SumRelated {
                            relation: rel.clone(),
                            current_slot: 1,
                            related_slot: 0,
                            value: RelatedValueRef::Input(field.clone()),
                            where_clause: None,
                        });
                    }
                }
                return Err(RacError::lower(
                    "sum(...) requires a relation field access argument".to_string(),
                ));
            }
            // Extension: filtered aggregation. The deployed DSL doesn't have a
            // `where` predicate on `sum` / `len`, so we surface filtered forms
            // as named function calls. Each takes a relation and an input
            // field name on the related entity that the caller pre-computes.
            //
            //   count_where(relation, is_qualifying)
            //   sum_where(relation, amount_field, is_qualifying)
            "count_where" => {
                if args.len() != 2 {
                    return Err(RacError::lower("count_where takes 2 args".to_string()));
                }
                let relation = match &args[0] {
                    Expr::Var(r) => r.clone(),
                    _ => return Err(RacError::lower("count_where arg 1 must be relation name".to_string())),
                };
                let pred = match &args[1] {
                    Expr::Var(p) => p.clone(),
                    _ => return Err(RacError::lower("count_where arg 2 must be predicate field name".to_string())),
                };
                ScalarExpr::CountRelated {
                    relation,
                    current_slot: 1,
                    related_slot: 0,
                    where_clause: Some(Box::new(JudgmentExpr::Comparison {
                        left: ScalarExpr::Input(pred),
                        op: ComparisonOp::Eq,
                        right: ScalarExpr::Literal(ScalarValue::Bool(true)),
                    })),
                }
            }
            "sum_where" => {
                if args.len() != 3 {
                    return Err(RacError::lower("sum_where takes 3 args".to_string()));
                }
                let relation = match &args[0] {
                    Expr::Var(r) => r.clone(),
                    _ => return Err(RacError::lower("sum_where arg 1 must be relation name".to_string())),
                };
                let field = match &args[1] {
                    Expr::Var(f) => f.clone(),
                    _ => return Err(RacError::lower("sum_where arg 2 must be amount field name".to_string())),
                };
                let pred = match &args[2] {
                    Expr::Var(p) => p.clone(),
                    _ => return Err(RacError::lower("sum_where arg 3 must be predicate field name".to_string())),
                };
                ScalarExpr::SumRelated {
                    relation,
                    current_slot: 1,
                    related_slot: 0,
                    value: RelatedValueRef::Input(field),
                    where_clause: Some(Box::new(JudgmentExpr::Comparison {
                        left: ScalarExpr::Input(pred),
                        op: ComparisonOp::Eq,
                        right: ScalarExpr::Literal(ScalarValue::Bool(true)),
                    })),
                }
            }
            _ => {
                return Err(RacError::lower(format!("unknown function `{}`", func)));
            }
        },
        Expr::Cond { condition, then_expr, else_expr } => ScalarExpr::If {
            condition: Box::new(lower_to_judgment(condition, ctx)?),
            then_expr: Box::new(lower_to_scalar(then_expr, ctx)?),
            else_expr: Box::new(lower_to_scalar(else_expr, ctx)?),
        },
        Expr::Match { subject, cases } => {
            // Lower as nested if/elif: match s: a => x, b => y
            //   → if s == a: x elif s == b: y else: (last)
            if cases.is_empty() {
                return Err(RacError::lower("empty match".to_string()));
            }
            let subj_scalar = lower_to_scalar(subject, ctx)?;
            let mut iter = cases.iter().rev();
            let (last_pat, last_res) = iter.next().unwrap();
            let mut expr = ScalarExpr::If {
                condition: Box::new(JudgmentExpr::Comparison {
                    left: subj_scalar.clone(),
                    op: ComparisonOp::Eq,
                    right: lower_to_scalar(last_pat, ctx)?,
                }),
                then_expr: Box::new(lower_to_scalar(last_res, ctx)?),
                else_expr: Box::new(ScalarExpr::Literal(ScalarValue::Integer(0))),
            };
            for (pat, res) in iter {
                expr = ScalarExpr::If {
                    condition: Box::new(JudgmentExpr::Comparison {
                        left: subj_scalar.clone(),
                        op: ComparisonOp::Eq,
                        right: lower_to_scalar(pat, ctx)?,
                    }),
                    then_expr: Box::new(lower_to_scalar(res, ctx)?),
                    else_expr: Box::new(expr),
                };
            }
            expr
        }
        Expr::FieldAccess { .. } => {
            return Err(RacError::lower(
                "bare field access in scalar position not supported".to_string(),
            ));
        }
    })
}

fn lower_to_judgment(e: &Expr, ctx: &LowerCtx) -> Result<JudgmentExpr, RacError> {
    Ok(match e {
        Expr::LitBool(b) => JudgmentExpr::Comparison {
            left: ScalarExpr::Literal(ScalarValue::Bool(*b)),
            op: ComparisonOp::Eq,
            right: ScalarExpr::Literal(ScalarValue::Bool(true)),
        },
        Expr::Var(name) => {
            if ctx.derived.contains(name) {
                JudgmentExpr::Derived(name.clone())
            } else {
                JudgmentExpr::Comparison {
                    left: ScalarExpr::Input(name.clone()),
                    op: ComparisonOp::Eq,
                    right: ScalarExpr::Literal(ScalarValue::Bool(true)),
                }
            }
        }
        Expr::BinOp { op, left, right } => match op {
            BinOpKind::And => JudgmentExpr::And(vec![
                lower_to_judgment(left, ctx)?,
                lower_to_judgment(right, ctx)?,
            ]),
            BinOpKind::Or => JudgmentExpr::Or(vec![
                lower_to_judgment(left, ctx)?,
                lower_to_judgment(right, ctx)?,
            ]),
            BinOpKind::Lt | BinOpKind::Gt | BinOpKind::Le | BinOpKind::Ge
            | BinOpKind::Eq | BinOpKind::Ne => {
                let l = lower_to_scalar(left, ctx)?;
                let r = lower_to_scalar(right, ctx)?;
                let cmp = match op {
                    BinOpKind::Lt => ComparisonOp::Lt,
                    BinOpKind::Gt => ComparisonOp::Gt,
                    BinOpKind::Le => ComparisonOp::Lte,
                    BinOpKind::Ge => ComparisonOp::Gte,
                    BinOpKind::Eq => ComparisonOp::Eq,
                    BinOpKind::Ne => ComparisonOp::Ne,
                    _ => unreachable!(),
                };
                JudgmentExpr::Comparison { left: l, op: cmp, right: r }
            }
            _ => {
                return Err(RacError::lower(format!(
                    "binary op {:?} in judgment position",
                    op
                )));
            }
        },
        Expr::UnaryOp { op, operand } => match op {
            UnaryOpKind::Not => JudgmentExpr::Not(Box::new(lower_to_judgment(operand, ctx)?)),
            _ => {
                return Err(RacError::lower("unary op in judgment position".to_string()));
            }
        },
        _ => {
            return Err(RacError::lower(format!(
                "expression shape not supported in judgment position: {:?}",
                std::mem::discriminant(e)
            )));
        }
    })
}

/// Convenience: parse a `.rac` file and lower to engine `Program`.
pub fn load_rac_file<P: AsRef<Path>>(path: P) -> Result<Program, RacError> {
    let module = parse_file(path)?;
    lower_module(&module)
}
