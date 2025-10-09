import logging
import traceback
from typing import Self

import disnake
from disnake.ext import commands
from disnake.ext.commands import InteractionBot
from result import Err

from absolute_unit.config import Config
from absolute_unit.conversion import try_convert_expression
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
        converted_result = try_convert_expression(input, target)
        if isinstance(converted_result, Err):
            return await interaction.send(
                converted_result.err_value, ephemeral=self.bot.config.ephemeral_errors
            )
        (expression, converted, has_currency) = converted_result.ok_value

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

        if verbose:
            output = f"```\n{input}\n```interpreting as\n```\n{expression}\n=\n{converted_str}\n```"
        else:
            output = f"`{input}` = `{converted_str}`"
        if has_currency:
            currency_cog = self.bot.currency_cog
            if currency_cog is not None:
                last_refresh = currency_cog.last_refresh_datetime
                if last_refresh is not None:
                    timestamp = int(last_refresh.timestamp())
                    output += f"\n-# Currency exchange rates as of <t:{timestamp}:t>"
        _ = await interaction.send(output)

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
