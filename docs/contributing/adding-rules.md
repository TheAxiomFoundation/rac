# Adding Rules

## Finding the Right Location

Rules are organized by statutory citation:

```
rac-us/
└── irc/
    └── subtitle_a/.../§<section>/
        ├── variables/
        │   └── <variable_name>.rac
        └── parameters/
            └── <parameter_name>.yaml
```

## Creating a Variable

1. Find the statutory section
2. Create the directory path
3. Write the variable file

```cosilico
# us/irc/.../§XX/(a)/variables/my_variable.rac

references:
  dep1: us/irc/.../other_variable
  param1: us/irc/.../§XX/(b)/my_parameter

variable my_variable {
  entity TaxUnit
  period Year
  dtype Money
  reference "26 USC § XX(a)"

  formula {
    return dep1 * param1
  }
}
```

## Adding Tests

Create matching YAML tests:

```yaml
# tests/us/irc/.../§XX/my_variable.yaml

tests:
  - name: Basic case
    period: 2024
    input:
      person: { age: 30, ... }
    output:
      my_variable: 1000
```

## Validation

```bash
cosilico check us/irc/.../§XX/
cosilico test tests/us/irc/.../§XX/
```
