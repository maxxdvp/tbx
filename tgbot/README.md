# Telegram Bot #

Telegram Bot for receiving trading notifications.


### How To Set Up ###

Register your telegram bot with Bot Father.

Put API key with name BOT_TOKEN to keyring under service with name specified in params.yml:

    keyring_service: TB-TGBot

Create in this folder file users.txt with telegram user id (or ids) allowed to use this bot. Each id on separated line.
The bot will tell you your id when you try to connect to it for the first time.

### How To Test ###

Just run tests/test_publisher.py.
It will send test messages to your bot.
