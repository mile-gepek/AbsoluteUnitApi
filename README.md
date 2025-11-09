
# AbsoluteUnit
AbsoluteUnit is a discord bot for converting arbitrary measurement units, powered by [pint](https://pypi.org/project/Pint/) and [disnake](https://disnake.dev/).

## Features

* A parser built to handle input adaptively (e.g. intepreting `5ft 9in` as `5*ft + 9*in`), an explanation can be found in the PARSING.md file.
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
Configuration is done through a `.env` file for secrets, and a `config.toml` file for general configuration.

### .env
| Key | Description | Optional |
| :-- | :-- | :-:  |
| BOT_TOKEN | The discord bot token. | No |
| CURRENCY_API_TOKEN | The currencyapi token.<br>Currency conversion will be disabled if the token is not found. | Yes |

### config.toml

| Key | Description | Optional | Default |
| :-- | :-- | :-:  | :-: |
| test_guild_ids | The list of guilds to register commands to when testing. | Yes | `[]` |
| mod_role_ids | A list of mod role ids.<br>Anyone with a mod role bypasses cooldowns | Yes | `[]` |
| admin_role_ids | A list of admin role ids.<br>Anyone with an admin role bypasses cooldowns, and can change configuration through commands. | Yes | `[]` |
| cooldown_duration | A float representing cooldown duration in seconds. | Yes | `5` |

Example config:
```toml
test-guild-ids = [123456789012345678]

admin_role_ids = [123456789012345678]

cooldown-duration = 6.7
```
