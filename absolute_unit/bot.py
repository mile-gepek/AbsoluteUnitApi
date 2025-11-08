import logging
import traceback
from typing import Callable, Self

import disnake
from disnake.ext import commands
from pint import UnitRegistry
from pint.facets.plain import PlainQuantity
from result import Err

from absolute_unit import conversion, currencies
from absolute_unit.config import Config, Settings
from absolute_unit.parsing import ParserMode


logger = logging.getLogger(__name__)


class Bot(commands.InteractionBot):
    def __init__(
        self,
        settings: Settings,
        config: Config,
        client: commands.InteractionBot,
        ureg: UnitRegistry,
    ) -> None:
        super().__init__(test_guilds=config.test_guild_ids)
        self.settings: Settings = settings
        self.config: Config = config
        self.ureg: UnitRegistry = ureg

        if config.test_guild_ids is None:
            logger.info("No test guilds specified, commands will be synced globally.")
        else:
            logger.info("Testing mode on, all errors will not be ephemeral.")

        self.currency_cog: currencies.CurrencyCog | None = None
        currency_api_token = settings.currency_api_token
        if currency_api_token is None:
            logger.info(
                "currencyapi token not found in config, currency conversion will be disabled."
            )
        else:
            self.currency_cog = currencies.CurrencyCog(self, currency_api_token, ureg)
            self.add_cog(self.currency_cog)
        self.add_cog(ConversionCog(self))

    @classmethod
    def default(cls) -> Self:
        settings = Settings.from_env().unwrap()
        config = Config.get_config().unwrap()
        client = commands.InteractionBot(test_guilds=config.test_guild_ids)
        ureg = UnitRegistry()
        return cls(settings, config, client, ureg)


def is_admin[T]() -> Callable[[T], T]:
    async def predicate(
        interaction: disnake.ApplicationCommandInteraction[Bot],
    ) -> bool:
        admin_role_ids = interaction.bot.config.admin_role_ids
        if isinstance(interaction.author, disnake.User):
            return True
        author_roles: disnake.utils.SnowflakeList = interaction.author._roles  # pyright: ignore[reportPrivateUsage]
        has_admin_role = any(author_roles.has(role) for role in admin_role_ids)
        if not has_admin_role:
            await interaction.send(
                "Only admins can change or view the cooldown.", ephemeral=True
            )
        return has_admin_role

    return commands.app_check(predicate)  # pyright: ignore[reportUnknownMemberType]


def cooldown_check(
    interaction: disnake.GuildCommandInteraction[Bot],
) -> commands.Cooldown | None:
    config = interaction.bot.config
    if config.testing_mode:
        return None

    # Member.roles seems to be bugged.
    # Raises `AttributeError: 'Object' object has no attribute 'get_role'`.
    author_roles = interaction.author._roles  # pyright: ignore[reportPrivateUsage]
    skip_roles = config.admin_role_ids + config.mod_role_ids
    if any(author_roles.has(role) for role in skip_roles):
        return None
    if not config.cooldown_duration:
        return None

    return commands.Cooldown(1, config.cooldown_duration)


class ConversionCog(commands.Cog):
    def __init__(self, bot: Bot):
        self.bot: Bot = bot

    # disnake's typing on dynamic_cooldown requires the check's argument to be Message,
    # but it allows (and should be typed to allow) interactions
    @commands.dynamic_cooldown(cooldown_check, commands.BucketType.member)  # pyright: ignore[reportArgumentType]
    @commands.slash_command()
    async def convert(
        self,
        interaction: disnake.GuildCommandInteraction[Bot],
        input: str,
        target: str | None = None,
        verbose: bool = False,
        mode: ParserMode = ParserMode.Adaptive,
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
        mode:
            Whether to make implicit operations use multiplication, or infer them from dimensionality.
        """
        # disnake passes a string instead of the enum variant
        mode = ParserMode(mode)

        ephemeral_errors = not self.bot.config.testing_mode

        # TODO: maybe clean this up by raising all errors, so the slash_command_error event can handle them
        expression_result = conversion.parse_input(input, self.bot.ureg, mode)
        if isinstance(expression_result, Err):
            error_message = f"```\n{input}\n{expression_result.err()}\n```"
            if target is not None:
                target_unit_result = conversion.get_target_unit(target, self.bot.ureg)
                if isinstance(target_unit_result, Err):
                    error = target_unit_result.err()
                    error_message += f"Target unit errors:```\n{error}\n```"
            return await interaction.send(error_message, ephemeral=ephemeral_errors)
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
            return await interaction.send(output, ephemeral=ephemeral_errors)
        evaluated: PlainQuantity[float] = evaluation_result.ok().to_reduced_units()  # pyright: ignore [reportUnknownVariableType, reportUnknownMemberType]

        if target is None:
            target_unit_result = conversion.infer_target_unit(evaluated, self.bot.ureg)
        else:
            target_unit_result = conversion.get_target_unit(target, self.bot.ureg)

        if isinstance(target_unit_result, Err):
            error = target_unit_result.err()
            output += f"Target unit errors:```\n{error}\n```"
            return await interaction.send(output, ephemeral=ephemeral_errors)
        target_unit = target_unit_result.ok()

        has_currency = conversion.has_different_currencies(
            self.bot.ureg,
            evaluated,
            target_unit,
        )

        conversion_result = conversion.convert(evaluated, target_unit)
        if isinstance(conversion_result, Err):
            output += str(conversion_result.err())
            return await interaction.send(output, ephemeral=ephemeral_errors)
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

        ephemeral = verbose and self.bot.config.test_guild_ids is None
        await interaction.send(output, ephemeral=ephemeral)

    @is_admin()
    @commands.slash_command()
    async def cooldown(
        self,
        interaction: disnake.ApplicationCommandInteraction[commands.InteractionBot],
        cooldown: commands.Range[float, 0, ...] | None = None,
    ) -> None:
        """
        Get or set the cooldown for the `convert` command.

        Parameters
        ----------
        cooldown:
            Positive number of seconds to set the cooldown duration to.
        """
        if cooldown is None:
            await interaction.send(
                f"Cooldown is set to {self.bot.config.cooldown_duration:.2f} seconds.",
                ephemeral=True,
            )
            return

        self.bot.config.cooldown_duration = cooldown
        self.bot.config.write()
        THRESHOLD: float = 10
        message = f"Cooldown set to {cooldown}."
        if cooldown > THRESHOLD:
            message += f"\n-# Cooldown higher than {THRESHOLD:.2f} seconds, is this intentional?"
        await interaction.send(message, ephemeral=True)

    @commands.Cog.listener()
    async def on_slash_command_error(
        self,
        interaction: disnake.ApplicationCommandInteraction[commands.InteractionBot],
        error: commands.CommandError,
    ) -> None:
        if isinstance(error, commands.CheckFailure):
            return

        # For some reason on_slash_command_error gets triggered on cooldowns even though CommandOnCooldown is not a subclass of CommandInvokeError
        if isinstance(error, commands.CommandOnCooldown):
            await interaction.send(
                f"Command on cooldown, please wait {error.retry_after:.2f} seconds.",
                ephemeral=True,
            )
            return

        logger.error(
            f"Error when attempting command '{interaction.application_command.name}': \"{error}\""
        )
        traceback.print_exception(error)

        if not isinstance(error, commands.CommandInvokeError):
            return

        original = error.original
        original_type_name = type(original).__name__
        original_message = str(original)
        if original_message:
            msg = f"Error when attempting command:\n`{original_type_name}: {original_message}`\nThis is a bug."
        else:
            msg = f"Error when attempting command:\n`{original_type_name}`\nThis is a bug."
        await interaction.send(msg, ephemeral=ephemeral_errors)

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        logger.info(f"Logged in as {self.bot.user} (ID: {self.bot.user.id})\n")
