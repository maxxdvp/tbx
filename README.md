# Trading Box eXperimental #

A modular Python framework for reliable algotraiding bots.

Detailed description is in the articles:
[1. Requirements and Workflow](https://wire.insiderfinance.io/engineering-an-algotrading-framework-1-requirements-and-workflow-32877183304a)
[2. Analyzer and Strategy](https://wire.insiderfinance.io/engineering-of-algotrading-framework-2-analyzer-and-strategy-64a353515060)
[3. Input Data Processing](https://wire.insiderfinance.io/engineering-of-algotrading-framework-3-input-data-processing-fd3d36b5742b)
[4. Agent Assembly](https://wire.insiderfinance.io/engineering-an-algotrading-framework-4-agent-assembly-b10cf23defe3)

### What in the repository ###

As for now, the trading system consists of trading agent(s) and telegram bot.
Telegram bot is used for receiving mobile notifications on transactions and critical events.

Folder structure in the order of dependency and corresponding parts of the framework:
```
.
├── connectors                         # Library for trading/data provider connectors
│   └── bybit                          # ByBit connector for the futures market
│       └── tests                      # Tests for the ByBit connector
├── agent                              # Base classes and helpers for trading agents
│   ├── tests                          # Tests for base classes and helpers
│   ├── indicators                     # Technical indicators for agent analyzers
│   └── agents                         # Agent implementations
│       └── analyzers                  # Analyzer implementations
├── constants                          # Common constants for the entire system
├── log                                # Logging classes and helpers
│   └── tests                          # Tests for the logging module
├── proto                              # Protocol Buffers for inter-service queues
├── tgbot                              # Telegram bot integration
│   └── tests                          # Tests for the Telegram bot
```

### How to set up and startup ###

Currently, one sample agent for ByBit futures market is implemented and ready to run.
What do you need before the first run:

1. [Compile Protocol Buffers files](./proto/README.md)
2. Set options in agent/agents/mean_reversal_oneway_bybit/params.yml
3. Make a dedicated account on ByBit, create API keys and add public API key with name API_KEY and private API key with name API_SECRET to keyring under service with name specified in params.yml/keyring_service
4. [Setup Telegram Bot](./tgbot/README.md)
5. Run tgbot/main.py
6. Run agent/agents/mean_reversal_oneway_bybit/main.py

Now you the agent is working, and you can watch for its work in ByBit GUI and with messages in the Telegam bot.
Also logging in terminal and agent/agents/mean_reversal_oneway_bybit/agent.log are available.

### Contributions ###

If you want to participate in the project, please [contact](maxx@dvp@gmail.com) me to discuss details.
