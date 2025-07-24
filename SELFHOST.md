# Self-hosting instructions

This guide explains all the necessary steps to self-host your own copy of the bot.

Broadly speaking, all you need to do is create your own Telegram Bot user (which
gives you an API token), obtain a Lunch Money API token, and run the application
(whether locally or on a server).

There are several reasons to run your own instance. The main and obvious one is that
you can ensure your Lunch Money token is private and that no one can see your transactions.

## How to create a Telegram bot

Creating a Telegram bot is super easy (and fun): there is a bot that creates bots called the
[BotFather](https://t.me/BotFather). All you need to do is tell it to create a new bot by sending
it the `/newbot` command.

It will ask you to provide a name for your bot (you can call it whatever you want)
and a username (the only constraint here is that it must not exist and it must end with "Bot").

Once you do that, it will give you an API token which you will need in the next steps.

### Optional

The commands menu of the Lonchera bot has to be set by the BotFather. You can do so by sending
the `/setcommands` command, choosing your bot, and then sending the following (you can customize this):

```
review_transactions - Check for unreviewed transactions
add_transaction - Adds a transaction manually
balances - Shows the current balances in all accounts
show_budget - Show the budget for the current month
settings - Changes the settings of the bot
```

## Running the bot

Clone the project: `git clone git@github.com:casidiablo/lonchera.git`

### Run manually, locally

You can run the bot locally on your own hardware. The Telegram API token can be provided as
an env var, or by writing it to a `.env` file at the root of the project:

```
TELEGRAM_BOT_TOKEN=<TOKEN PROVIDED BY BOTFATHER>
```

The bot is written in Python. Make sure to install its dependencies first:

```
pip install -r requirements.txt
python main.py
```

## Run it using Docker

The `./run_using_docker.sh` script is provided to build and run the application in Docker as a daemon.

There's no magic to it. It literally builds the image and the runs it like this:

```
docker build -t lonchera .

docker run -d \
    -v "${DATA_DIR}:/data" \
    -e DB_PATH=/data/lonchera.db \
    -e TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN}" \
    -e DEEPINFRA_API_KEY="${DEEPINFRA_API_KEY}" \
    --name lonchera \
    lonchera
```

The script also automates the stopping of a previously run instance, and streams the logs of the container
after it starts.

## Host it in fly.io, for free

Fly.io has a very generous free tier, which should be more than enough to run your own instance of the bot.
They do ask for a credit card, but in theory you should not be charged if you run only this bot.

I provide a `fly.toml` file to get you started. So after creating an account in fly.io, and
[installing the flyctl tool](https://fly.io/docs/flyctl/install/), follow this steps to
launch a new instance of the app:


1. Create the deployment:

```
fly launch --name SOMETHING_CREATIVE --max-concurrent 1 --no-deploy
```

> If you don't feel creative, replace `--name SOMETHING_CREATIVE` with `--generate-name`.

Which will display something like:

```
An existing fly.toml file was found for app lonchera
? Would you like to copy its configuration to the new app? (y/N) 
```

To which you must say: `y`. And then it will show you some defaults, which I recommend you leave as is.

This will create a new app in fly.io with the name provided, but will not run it yet.

> This will modify the fly.toml file a bit (changing the name of the app). This is normal.

2. Provide the credentials

```
fly secrets set TELEGRAM_BOT_TOKEN=<TOKEN PROVIDED BY BOTFATHER>
```

Optionally, set a https://deepinfra.com/ API token which enables the AI-categorize feature,
which uses an LLM to find you the best category for a particular transaction:

```
fly secrets set DEEPINFRA_API_KEY=<SOME SECRET>
```

3. Actually run the application:

```
fly deploy
```

(or better yet, use the `run_using_fly.sh`)

This will build the app using Docker, create a volume to store the DB, and deploy the bot to fly.io.

At the end of you should see a message like this:

```
Finished launching new machines
-------
Checking DNS configuration for lively-wildflower-275.fly.dev

Visit your newly deployed app at https://lively-wildflower-275.fly.dev/
```

But instead of `lively-wildflower-275` it will be the name of your app.

If you go to that URL you should see the status of your bot, which should be
something like this:

```md
#status

bot: @YourBotNameBot
db size: 0.01 MB
uptime: 5 seconds ago
version: 1.0.0-c45ebdc (dirty)
commit: c45ebdc
bot token: 7512...k33U
ai status: AI enabled (key: ibvL...SLDz)
bot status: running
```
