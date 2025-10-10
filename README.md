
# AbsoluteUnit
AbsoluteUnit is a discord bot for converting arbitrary measurement units, powered by [pint](https://pypi.org/project/Pint/) and [disnake](https://disnake.dev/).

It features a custom parser which tries to parse expressions in a "human-friendly" way,
e.g. parsing `5ft 9in`  as `5*ft + 9*in`, the exact parsing rules can be found in the [parsing](#parsing) section.


## Features

* Arbitrary unit conversion, with a huge set of units available by default, and easy way to define new units.
* Currency conversion via [currencyapi](https://currencyapi.com) when [configured](#configuration) with an API key, exchange rates refreshed every 24 hours.


## Getting started

### Installation

Select your environment from the list below to view installation instructions.

<details>
<summary>Pip and other python package managers</summary>

The project features a `pyproject.toml` file for use with standard python tools, such as pip.

To install the necessary dependencies with pip (preferably in a [virtual environment](https://docs.python.org/3/tutorial/venv.html)), run

```sh
pip install .
```

</details>

<details>
<summary>Nix</summary>

The repository includes a nix flake which pulls in dependencies from the `pyproject.toml` file.\
To enter the development environment, run

```sh
nix develop
```
This will install the necessary packages the first time, and start the environment, after which you can run the bot.

</details>

### Running

After installing the dependencies and [configuring](#configuration), run the bot with
```sh
python -m absolute_unit
```


## Configuration
Configuration is currently done only through a `.env` file at the root directory, with the following keys:
```
DISCORD_APPLICATION_TOKEN `str`
    - The token for the discord bot.

CURRENCYAPI_TOKEN `Optional str`
    - The token for currencyapi.
    - Currency conversion will be disabled if this token is not found.

TEST_GUILD_ID: `Optional int`
    - ID of the guild used for testing.
    - The test guild ID will enable testing mode, which disables ephemeral errors, except for command cooldowns.
```


## Parsing
The "human-friendly" parsing tries to make the bot easier to use for common use cases by interpreting implicit operations differently based on the expression's dimensionality (e.g. length, time, length / time).\

These rules are definitely not perfect, possibly leading to odd interpretations.\
Because of this, the `convert` command features a verbose mode which will print out the interpreted expression for debugging purposes.\
Suggestions are always welcome, and I hope the system is good enough for everyday use.

Regular mathematical expressions should work like expected, if you run into any issues with that, please submit an issue.

### Rules
####  Primary chains
A primary chain is a series of number and unit expressions, where number and unit expressions get parsed as if they were standalone expressions. It can be of single number or unit expressions, or a series of primary pairs.

Primary chains are the "building blocks" of expressions.

| Expression type | Input         | Interpretation              |
| :-------------- | :-----------: | :-------------------------: |
| Number          | `1\2`         | $\frac12$                   |
| Unit            | `km/h**2`     | $\frac{km}{h^2}$            |
| Primary pair    | `1/2 km/h**2` | $\frac{1}{2}\frac{km}{h^2}$ |
> These smaller expressions only include division `/` and exponentiation `**` operations, multiplication is handled separately.

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

Because the primary chains are parsed first, the parser can be used in the following way:

| Input                      | Interpretation                   | 
| :------------------------: | :------------------------------: |
|`1 mile 300 yard / 2h 13min`| $\frac{1mi + 300yd}{2h + 13min}$ |

<br>

#### PEMDAS
After all primary chains are found, expressions are further built from them following standard PEMDAS rules.
