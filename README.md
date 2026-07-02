
# AbsoluteUnit
AbsoluteUnit is a API for converting arbitrary measurement units, powered by [pint](https://pypi.org/project/Pint/).

## Features

* A parser built with two modes:
  * Strict (the default) - Strict PEMDAS rules, concatenation is always multiplication.
  * Adaptive - Attempts to handle expressions like common english language (e.g. intepreting `5ft 9in` as `5*ft + 9*in`), an explanation can be found in the PARSING.md file.
* Arbitrary unit conversion, with a huge set of units available by default.
* Currency conversion via [currencyapi](https://currencyapi.com) when [configured](#configuration) with an API key, exchange rates refreshed every 24 hours.


## Getting started

### Installation


#### Pip or other package managers

The project features a `pyproject.toml` file for use with standard python tools, such as pip.

To install the necessary dependencies with pip (preferably in a [virtual environment](https://docs.python.org/3/tutorial/venv.html)), run

```sh
pip install .
```

### Running

After installing the dependencies and [configuring](#configuration), run the API with
```sh
python -m api
```

#### Running with docker
The project includes a small docker compose configuration, which can be started using
```sh
docker compose up --build api -d
```

The `api` service also restarts after reboot, unless stopped manually.

## Configuration
Configuration is done through a `.env` file for secrets, and a `config.toml` file for general configuration.

### .env
| Key | Description | Optional |
| :-- | :-- | :-:  |
| CURRENCY_API_TOKEN | The currencyapi token.<br>Currency conversion will be disabled if the token is not found, and currencies will be treated as unknown unit errors. | Yes |

### config.toml

| Key | Description | Optional | Default |
| :-- | :-- | :-:  | :-: |
| debug | Enables debug mode, which activates hot reloading. | Yes | False |
| log_level | The default severity level for logging. | Yes | `"warning"` |

Example:
```toml
debug = false

log_level = "error"
```
