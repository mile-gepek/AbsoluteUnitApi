from absolute_unit.bot import Bot

def main() -> int:
    bot = Bot.default()
    bot.run()

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
