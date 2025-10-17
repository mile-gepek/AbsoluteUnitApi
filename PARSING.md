

# Parsing
The "human-friendly" parsing tries to make the bot easier to use for common use cases by interpreting implicit operations differently based on the expression's dimensionality.

## Rules
These rules are definitely not perfect, possibly leading to odd interpretations.\
Because of this, the `convert` command features a verbose mode which will print out the interpreted expression for debugging purposes.\
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
