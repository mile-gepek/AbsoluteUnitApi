
# AbsoluteUnit
AbsoluteUnit is a discord bot for converting arbitrary measurement units, powered by [pint](https://pypi.org/project/Pint/) and [disnake](https://disnake.dev/).

It features a custom parser which tries to parse expressions in a "human-friendly" way,
e.g. parsing `5ft 9in`  as `5*ft + 9*in`, an explanation of the parsing rules can be found in the PARSING.md file.


## Features

* A parser built to handle "human language-esque" input (e.g. `5ft 9in`), an explanation can be found in the PARSING.md file.
* Arbitrary unit conversion, with a huge set of units available by default.
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
