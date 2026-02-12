"""Native compilation for maximum performance.

Compiles IR to native Rust binary. Auto-installs Rust toolchain if needed.

Performance: ~40M rows/sec with numpy arrays.
"""

import hashlib
import json
import os
import platform
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .codegen.rust import generate_rust
from .compiler import IR

CACHE_DIR = Path.home() / ".cache" / "rac"
RUSTUP_URL = "https://sh.rustup.rs"


def _get_cargo() -> Path | None:
    cargo = shutil.which("cargo")
    if cargo:
        return Path(cargo)
    cargo_home = Path.home() / ".cargo" / "bin" / "cargo"
    if cargo_home.exists():
        return cargo_home
    return None


def _install_rust() -> Path:
    print("Installing Rust toolchain (one-time setup)...")
    if platform.system() == "Windows":
        import urllib.request

        rustup_init = CACHE_DIR / "rustup-init.exe"
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve("https://win.rustup.rs/x86_64", rustup_init)
        subprocess.run([str(rustup_init), "-y", "--quiet"], check=True)
    else:
        subprocess.run(
            [
                "sh",
                "-c",
                f"curl --proto '=https' --tlsv1.2 -sSf {RUSTUP_URL} | sh -s -- -y --quiet",
            ],
            check=True,
            capture_output=True,
        )
    cargo = Path.home() / ".cargo" / "bin" / "cargo"
    if not cargo.exists():
        raise RuntimeError("Failed to install Rust")
    print("Rust installed successfully")
    return cargo


def ensure_cargo() -> Path:
    cargo = _get_cargo()
    if cargo:
        return cargo
    return _install_rust()


def _ir_hash(ir: IR) -> str:
    data = json.dumps(
        {"order": ir.order, "vars": {k: str(v.expr) for k, v in ir.variables.items()}},
        sort_keys=True,
    )
    return hashlib.sha256(data.encode()).hexdigest()[:16]


class CompiledBinary:
    """A compiled RAC binary for maximum performance."""

    def __init__(
        self,
        binary_path: Path,
        ir: IR,
        entity_schemas: dict[str, list[str]],
        entity_outputs: dict[str, list[str]],
    ):
        self.binary_path = binary_path
        self.ir = ir
        self.entity_schemas = entity_schemas
        self.entity_outputs = entity_outputs

    def run(self, data: dict[str, list[dict]] | dict[str, np.ndarray]) -> dict[str, np.ndarray]:
        results = {}

        for entity_name, rows in data.items():
            if entity_name not in self.entity_outputs:
                continue

            input_fields = self.entity_schemas.get(entity_name, [])
            output_fields = self.entity_outputs[entity_name]

            if isinstance(rows, np.ndarray):
                input_arr = rows.astype(np.float64, copy=False)
                n_rows = len(input_arr)
            else:
                n_rows = len(rows)
                if n_rows == 0:
                    results[entity_name] = np.zeros((0, len(output_fields)), dtype=np.float64)
                    continue
                input_arr = np.array(
                    [[float(row.get(field, 0.0)) for field in input_fields] for row in rows],
                    dtype=np.float64,
                )

            input_path = tempfile.mktemp(suffix=".bin")
            with open(input_path, "wb") as f:
                f.write(struct.pack("<Q", n_rows))
                input_arr.tofile(f)

            output_path = tempfile.mktemp(suffix=".bin")

            try:
                result = subprocess.run(
                    [str(self.binary_path), entity_name, input_path, output_path],
                    capture_output=True,
                    text=True,
                )
                if result.returncode != 0:
                    raise RuntimeError(f"Binary failed for {entity_name}: {result.stderr}")

                with open(output_path, "rb") as f:
                    out_n = struct.unpack("<Q", f.read(8))[0]
                    output_arr = np.fromfile(f, dtype=np.float64).reshape(out_n, len(output_fields))

                results[entity_name] = output_arr
            finally:
                os.unlink(input_path)
                if os.path.exists(output_path):
                    os.unlink(output_path)

        return results


def compile_to_binary(ir: IR, cache: bool = True) -> CompiledBinary:
    cargo = ensure_cargo()

    entity_schemas: dict[str, list[str]] = {}
    entity_outputs: dict[str, list[str]] = {}

    for path in ir.order:
        var = ir.variables[path]
        if var.entity:
            entity_outputs.setdefault(var.entity, []).append(path)

    for entity_name in entity_outputs:
        entity = ir.schema_.entities.get(entity_name)
        entity_schemas[entity_name] = list(entity.fields.keys()) if entity else []

    ir_hash = _ir_hash(ir)
    project_dir = CACHE_DIR / "projects" / ir_hash

    binary_name = "rac_native.exe" if platform.system() == "Windows" else "rac_native"
    binary_path = project_dir / "target" / "release" / binary_name

    if cache and binary_path.exists():
        return CompiledBinary(binary_path, ir, entity_schemas, entity_outputs)

    project_dir.mkdir(parents=True, exist_ok=True)

    (project_dir / "Cargo.toml").write_text("""[package]
name = "rac_native"
version = "0.1.0"
edition = "2021"

[dependencies]
rayon = "1.10"

[profile.release]
lto = true
codegen-units = 1
""")

    rust_code = generate_rust(ir)
    main_code = _generate_main(ir, entity_schemas, entity_outputs)
    full_code = "#![allow(unused_parens, unused_imports, unused_variables, unused_mut)]\n\n" + rust_code + "\n" + main_code

    src_dir = project_dir / "src"
    src_dir.mkdir(exist_ok=True)
    (src_dir / "main.rs").write_text(full_code)

    print("Compiling native binary...")
    result = subprocess.run(
        [str(cargo), "build", "--release", "--quiet"],
        cwd=project_dir,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(f"Compilation failed:\n{result.stderr}")

    print("Compilation complete")
    return CompiledBinary(binary_path, ir, entity_schemas, entity_outputs)


def _generate_main(
    ir: IR,
    entity_schemas: dict[str, list[str]],
    entity_outputs: dict[str, list[str]],
) -> str:
    entity_handlers = []

    for entity_name, input_fields in entity_schemas.items():
        output_fields = entity_outputs.get(entity_name, [])
        if not output_fields:
            continue

        type_name = "".join(part.capitalize() for part in entity_name.split("_"))
        n_inputs = len(input_fields)
        n_outputs = len(output_fields)

        entity_schema = ir.schema_.entities.get(entity_name)
        field_reads = []
        for i, f in enumerate(input_fields):
            is_int = entity_schema and f in entity_schema.fields and entity_schema.fields[f].dtype == "int"
            cast = " as i64" if is_int else ""
            field_reads.append(f"                    {f}: row[{i}]{cast},")

        output_writes = [
            f"            out[{i}] = o.{path.replace('/', '_')};"
            for i, path in enumerate(output_fields)
        ]

        entity_handlers.append(f'''
        "{entity_name}" => {{
            let n_input_fields = {n_inputs};
            let n_output_fields = {n_outputs};

            let mut input_data = vec![0.0f64; n_rows * n_input_fields];
            for i in 0..n_rows * n_input_fields {{
                file.read_exact(&mut buf8).expect("Failed to read");
                input_data[i] = f64::from_le_bytes(buf8);
            }}

            let mut output_data = vec![0.0f64; n_rows * n_output_fields];

            input_data
                .par_chunks(n_input_fields)
                .zip(output_data.par_chunks_mut(n_output_fields))
                .for_each(|(row, out)| {{
                    let input = {type_name}Input {{
{chr(10).join(field_reads)}
                    }};
                    let o = {type_name}Output::compute(&input, &scalars);
{chr(10).join(output_writes)}
                }});

            // Write output
            out_file.write_all(&(n_rows as u64).to_le_bytes()).unwrap();
            for v in output_data {{
                out_file.write_all(&v.to_le_bytes()).unwrap();
            }}
        }}''')

    return f"""
use rayon::prelude::*;
use std::env;
use std::fs::File;
use std::io::{{Read, Write, BufReader, BufWriter}};

fn main() {{
    let args: Vec<String> = env::args().collect();
    if args.len() != 4 {{
        eprintln!("Usage: {{}} <entity> <input.bin> <output.bin>", args[0]);
        std::process::exit(1);
    }}

    let entity = &args[1];
    let mut file = BufReader::new(File::open(&args[2]).expect("Failed to open input"));
    let mut out_file = BufWriter::new(File::create(&args[3]).expect("Failed to create output"));

    let mut buf8 = [0u8; 8];
    file.read_exact(&mut buf8).expect("Failed to read count");
    let n_rows = u64::from_le_bytes(buf8) as usize;

    let scalars = Scalars::compute();

    match entity.as_str() {{
{chr(10).join(entity_handlers)}
        _ => {{
            eprintln!("Unknown entity: {{}}", entity);
            std::process::exit(1);
        }}
    }}
}}
"""
