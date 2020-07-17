# circleci-logs
CircleCI log and security configuration automations.

`circleci-logs.py` - Downloads build logs from circleci for a particular project and repo.

`circleci-repos.py` - Checks a Github org for repos, or members of the org with personal repos, which have projects on CircleCI.

`circleci-vulnerable-config.py` - Checks a CircleCI project for signs of vulnerable configuration in regards to fork behaviour and secrets.

## Usage
You will need `requests` and 'pendulum' e.g.:

`pip install requests`
`pip install pendulum`

The `circleci-logs.py` scripts writes the log output to `./out/circleci/ORG/REPO/BUILD_NUM`.
