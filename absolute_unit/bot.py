import logging
import traceback
from typing import Callable, Self

import disnake
from disnake.ext import commands
from disnake.ext.commands import BucketType, Cooldown, InteractionBot, dynamic_cooldown
from pint import UnitRegistry
from pint.facets.plain import PlainQuantity
from result import Err

from absolute_unit import conversion, currencies
from absolute_unit.config import Config


logger = logging.getLogger(__name__)


class Bot(commands.InteractionBot):
    def __init__(
        self, config: Config, client: InteractionBot, ureg: UnitRegistry
    ) -> None:
        super().__init__(test_guilds=config.test_guilds)
        self.config: Config = config
        self.ureg: UnitRegistry = ureg

        if config.test_guilds is None:
            logger.info("No test guilds specified, commands will be synced globally.")
        else:
            logger.info("Testing mode on, all errors will not be ephemeral.")

        self.currency_cog: currencies.CurrencyCog | None = None
        currencyapi_token = config.currencyapi_token
        if currencyapi_token is None:
            logging.info(
                "currencyapi token not found in config, currency conversion will be disabled."
            )
        else:
            self.currency_cog = currencies.CurrencyCog(self, currencyapi_token, ureg)
            self.add_cog(self.currency_cog)
        self.add_cog(ConversionCog(self))

    @classmethod
    def default(cls) -> Self:
        config = Config.get_config().unwrap()
        client = InteractionBot(test_guilds=config.test_guilds)
        ureg = UnitRegistry()
        return cls(config, client, ureg)


def cooldown_check(
    interaction: disnake.ApplicationCommandInteraction[Bot],
) -> commands.Cooldown | None:
    if interaction.bot.config.testing_mode:
        return None
    return commands.Cooldown(1, 5)


class ConversionCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot

    # disnake's typing on dynamic_cooldown requires the check's argument to be Message,
    # but it allows (and should be typed to allow) interactions
    @dynamic_cooldown(cooldown_check, BucketType.member)  # pyright: ignore[reportArgumentType]
    @commands.slash_command()
    async def convert(
        self,
        interaction: disnake.GuildCommandInteraction[Bot],
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
        # TODO: maybe clean this up by raising all errors, so the slash_command_error event can handle them
        expression_result = conversion.parse_input(input, self.bot.ureg)
        if isinstance(expression_result, Err):
            error_message = f"```\n{input}\n{expression_result.err()}\n```"
            if target is not None:
                target_unit_result = conversion.get_target_unit(target, self.bot.ureg)
                if isinstance(target_unit_result, Err):
                    error = target_unit_result.err()
                    error_message += f"Target unit errors:```\n{error}\n```"
            return await interaction.send(
                error_message, ephemeral=self.bot.config.testing_mode
            )
        expression = expression_result.ok()

        output = ""
        if verbose:
            output = f"```\n{input}\n```interpreting as\n```\n{expression}\n```\n"

        evaluation_result = conversion.evaluate_expression(expression, self.bot.ureg)
        if isinstance(evaluation_result, Err):
            error_message = f"```\n{input}\n{evaluation_result.err()}\n```"
            if target is not None:
                target_unit_result = conversion.get_target_unit(target, self.bot.ureg)
                if isinstance(target_unit_result, Err):
                    error = target_unit_result.err()
                    error_message += f"Target unit errors:```\n{error}\n```"
            output += error_message
            return await interaction.send(
                output, ephemeral=self.bot.config.testing_mode
            )
        evaluated: PlainQuantity[float] = evaluation_result.ok().to_reduced_units()  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType]

        if target is None:
            target_unit_result = conversion.infer_target_unit(evaluated, self.bot.ureg)
        else:
            target_unit_result = conversion.get_target_unit(target, self.bot.ureg)

        if isinstance(target_unit_result, Err):
            error = target_unit_result.err()
            output += f"Target unit errors:```\n{error}\n```"
            return await interaction.send(
                output, ephemeral=self.bot.config.testing_mode
            )
        target_unit = target_unit_result.ok()

        has_currency = conversion.has_different_currencies(
            self.bot.ureg,
            evaluated,
            target_unit,
        )

        conversion_result = conversion.convert(evaluated, target_unit)
        if isinstance(conversion_result, Err):
            output += str(conversion_result.err())
            return await interaction.send(
                output, ephemeral=self.bot.config.testing_mode
            )
        converted = conversion_result.ok()

        # TODO: move allodis to a bigh "post-process" function
        if converted.units == self.bot.ureg.foot:
            magnitude = converted.magnitude
            whole = int(magnitude)
            quantity_foot = whole * self.bot.ureg.foot  # pyright: ignore[reportUnknownVariableType]
            decimal = magnitude - whole
            quantity_inch = decimal * 12 * self.bot.ureg.inch  # pyright: ignore[reportUnknownVariableType]
            converted_str = f"{quantity_foot:~P} {quantity_inch:.3g~P}"
        else:
            if converted.units == self.bot.ureg.kph:
                converted = converted.to("km/h")  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
            converted_str = f"{converted:.3g~P}"

        output += f"`{input}` = `{converted_str}`\n"

        same_unit = evaluated.unit_items() == target_unit.unit_items()
        if same_unit and target:
            output += "-# The input's unit and target unit are the same!"

        if has_currency:
            currency_cog = self.bot.currency_cog
            if currency_cog is not None:
                last_refresh = currency_cog.last_refresh_datetime
                if last_refresh is not None:
                    timestamp = int(last_refresh.timestamp())
                    output += f"-# Currency exchange rates as of <t:{timestamp}:t>"

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
        await interaction.send(msg, ephemeral=self.bot.config.testing_mode)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        print(f"Logged in as {self.bot.user} (ID: {self.bot.user.id})\n")
