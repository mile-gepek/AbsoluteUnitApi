

# Parsing
The expression parser has 2 modes of function:

- Adapative - The adaptive parsing tries to make the API easier for common everyday use cases by interpreting implicit operations differently based on the expression's dimensionality.
- Strict - Strict parsing treats any implicit operation as multiplication, excluding  number expressions next to each other.

## Rules for adaptive parsing
These rules are definitely not perfect, possibly leading to odd interpretations.\
Because of this, the `convert` endpoint includes the final intepretation of the expression in the response.\
I hope the system is good enough for everyday use, and suggestions are always welcome.

Regular mathematical expressions should work like expected, if you run into any issues with that, please submit an issue.

###  Primary chains
A primary chain is a series of number and unit expressions, where number and unit expressions get parsed as if they were standalone expressions. It can be of single number or unit expressions, or a primary pair (an implicitly multiplied number and unit expression).

Primary chains are the "building blocks" of expressions.

| Expression type | Input         | Interpretation              |
| :-------------- | :-----------: | :-------------------------: |
| Number          | `1/2`         | $\frac12$                   |
| Unit            | `km/h**2`     | $\frac{km}{h^2}$            |
| Primary pair    | `1/2 km/h**2` | $\frac{1}{2}\frac{km}{h^2}$ |
> These smaller expressions only include division `/` and exponentiation `**` operations.

<br>

If a primary chain consists of 2 primary pairs of the same dimensionality, they are added, and otherwise multiplied.

| Dimensionality | Input         | Interpretation                  |
| :------------- | :-----------: | :-----------------------------: |
| Same           | `5km/h 9cm/s` | $5\frac{km}{h} + 9\frac{cm}{s}$ |
| Different      | `5km 3h`      | $5 km \cdot 3h$                 |

  <br>
  
Primary pairs are combined left to right.

| Input        | Interpretation                  | 
| :----------: | :-----------------------------: |
|`5km/h 5h 3km`| $(5\frac{km}{h}\cdot 5h) + 3km$ |

> The expression `5km/h 5h` results in a quantity of length

<br>

Because primary chains are parsed first, the parser can be used in the following way:

| Input                      | Interpretation                   | 
| :------------------------: | :------------------------------: |
|`1 mile 300 yard / 2h 13min`| $\frac{1mi + 300yd}{2h + 13min}$ |

> `1mile 300yard` is one primary chain, and `2h 13min` is another.

<br>

### Further parsing
Further expressions are built from these chains with regular PEMDAS rules, and implicit multiplication.


## Rules for strict parsing.

Strict parsing does not rely on primary chains,  but rather singular numbers and units.

Implicit operations are always treated as multiplication, unless there are 2 numbers next to each other, in which case the parser will return an error.

### Examples
| Input    | Interpretation |
| :-: | :-: |
| `5ft 9in` | $5 \cdot ft \cdot 9 \cdot in$ |
