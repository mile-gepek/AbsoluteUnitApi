import logging
import traceback
from typing import Self

import disnake
from disnake.ext import commands
from disnake.ext.commands import InteractionBot
from result import Err
from rich.pretty import pprint

from absolute_unit import conversion
from absolute_unit.config import Config
from absolute_unit import ureg, currencies


logger = logging.getLogger(__name__)


class Bot:
    def __init__(self, config: Config, client: InteractionBot) -> None:
        self.config: Config = config
        self.client: InteractionBot = client

        self.currency_cog: currencies.CurrencyCog | None = None
        currencyapi_token = config.currencyapi_token
        if currencyapi_token is None:
            logging.info(
                "currencyapi token not found in config, currency conversion will be disabled."
            )
        else:
            self.currency_cog = currencies.CurrencyCog(
                self.client, currencyapi_token, ureg
            )
            self.client.add_cog(self.currency_cog)
        self.client.add_cog(ConversionCog(self))

    @classmethod
    def default(cls) -> Self:
        config = Config.get_config().unwrap()
        if config.test_guilds is None:
            logger.info("No test guilds specified, commands will be synced globally.")
        else:
            logger.info("Testing mode on, all errors will not be ephemeral.")

        client = InteractionBot(test_guilds=config.test_guilds)
        return cls(config, client)

    def run(self) -> None:
        self.client.run(self.config.bot_token)


class ConversionCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot

    @commands.cooldown(1, 5, commands.BucketType.channel)
    @commands.slash_command()
    async def convert(
        self,
        interaction: disnake.GuildCommandInteraction[commands.InteractionBot],
        input: str,
        # TODO: converters can be used here
        target: str | None = None,
        verbose: bool = False,
    ) -> None:
        """
        Convert the input expression.

        Parameters
        ----------
        input:
            The input expression to evaluate and convert.
        target:
            The output unit, infered if not specified.
        verbose:
            Print the intepretation of the parsed expression. Use this if output is unexpected.
        """
        expression_result = conversion.parse_input(input)
        if isinstance(expression_result, Err):
            error_message = f"```\n{input}\n{expression_result.err()}\n```"
            if target is not None:
                target_unit_result = conversion.get_target_unit(target)
                if isinstance(target_unit_result, Err):
                    error = target_unit_result.err()
                    error_message += f"Target unit errors:```\n{error}\n```"
            return await interaction.send(
                error_message, ephemeral=self.bot.config.ephemeral_errors
            )
        expression = expression_result.ok()

        output = ""
        if verbose:
            output = f"```\n{input}\n```interpreting as\n```\n{expression}\n```\n"

        evaluation_result = conversion.evaluate_expression(expression)
        if isinstance(evaluation_result, Err):
            error_message = f"```\n{input}\n{evaluation_result.err()}\n```"
            if target is not None:
                target_unit_result = conversion.get_target_unit(target)
                if isinstance(target_unit_result, Err):
                    error = target_unit_result.err()
                    error_message += f"Target unit errors:```\n{error}\n```"
            output += error_message
            return await interaction.send(
                output, ephemeral=self.bot.config.ephemeral_errors
            )
        evaluated = evaluation_result.ok()

        if target is None:
            target_unit_result = conversion.infer_target_unit(evaluated)
        else:
            target_unit_result = conversion.get_target_unit(target)

        if isinstance(target_unit_result, Err):
            error = target_unit_result.err()
            output += f"Target unit errors:```\n{error}\n```"
            return await interaction.send(
                output, ephemeral=self.bot.config.ephemeral_errors
            )
        target_unit = target_unit_result.ok()

        conversion_result = conversion.convert(evaluated, target_unit)
        if isinstance(conversion_result, Err):
            output += conversion_result.err()
            return await interaction.send(
                output, ephemeral=self.bot.config.ephemeral_errors
            )
        converted = conversion_result.ok()

        has_currency = "[currency]" in target_unit

        # TODO: move allodis to a bigh "post-process" function
        if converted.units == ureg.foot:
            magnitude = converted.magnitude
            whole = int(magnitude)
            quantity_foot = whole * ureg.foot  # pyright: ignore[reportUnknownVariableType]
            decimal = magnitude - whole
            quantity_inch = decimal * 12 * ureg.inch  # pyright: ignore[reportUnknownVariableType]
            converted_str = f"{quantity_foot:~P} {quantity_inch:.3g~P}"
        else:
            if converted.units == ureg.kph:
                converted = converted.to("km/h")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            converted_str = f"{converted:.3g~P}"

        output += f"`{input}` = `{converted_str}`"

        if has_currency:
            currency_cog = self.bot.currency_cog
            if currency_cog is not None:
                last_refresh = currency_cog.last_refresh_datetime
                if last_refresh is not None:
                    timestamp = int(last_refresh.timestamp())
                    output += f"\n-# Currency exchange rates as of <t:{timestamp}:t>"

        ephemeral = verbose and self.bot.config.test_guilds is None
        await interaction.send(output, ephemeral=ephemeral)

    @commands.Cog.listener()
    async def on_slash_command_error(
        self,
        interaction: disnake.ApplicationCommandInteraction[commands.InteractionBot],
        error: commands.CommandInvokeError,
    ) -> None:
        # For some reason on_slash_command_error gets triggered on cooldowns even though CommandOnCooldown is not a subclass of CommandInvokeError
        if isinstance(error, commands.CommandOnCooldown):
            await interaction.send(
                f"Command on cooldown, please wait {error.retry_after:.2f} seconds.",
                ephemeral=True,
            )
            return

        logging.error(
            f"Error when attempting command '{interaction.application_command.name}': \"{error}\""
        )
        traceback.print_exception(error)

        original = error.original
        original_type_name = type(original).__name__
        original_message = str(original)
        if original_message:
            msg = f"Error when attempting command:\n`{original_type_name}: {original_message}`\nThis is a bug."
        else:
            msg = f"Error when attempting command:\n`{original_type_name}`\nThis is a bug."
        await interaction.send(msg, ephemeral=self.bot.config.ephemeral_errors)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Logged in as {self.bot.client.user} (ID: {self.bot.client.user.id})\n")
