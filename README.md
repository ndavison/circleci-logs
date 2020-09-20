# circleci-logs
CircleCI log and security configuration automations.

`circleci-logs.py` - Downloads build logs from circleci for a particular project and repo.

`circleci-repos.py` - Checks a Github org for repos, or members of the org with personal repos, which have projects on CircleCI.

`circleci-vulnerable-config.py` - Checks a CircleCI project for signs of vulnerable configuration in regards to fork behaviour and secrets. More info on this can be found here: https://nathandavison.com/blog/shaking-secrets-out-of-circleci-builds

## Usage
You will need `requests` and `pendulum` e.g.:

`pip install requests`

`pip install pendulum`

The `circleci-logs.py` scripts writes the log output to `./out/circleci/ORG/REPO/BUILD_NUM`.

## Typical workflow

  1. Use 'circleci-repos.py' to collect a target's CircleCI repos.
  1. Use the output from #1 to collect the logs using `circleci-logs.py`.
  1. Use the output from #1 to check for signs of vulnerable fork PR configuration using `circleci-vulnerable-config.py`.
  1. ???? (search logs for keys/tokens, manually confirm vulnerable projects from #3).
  1. Profit.
