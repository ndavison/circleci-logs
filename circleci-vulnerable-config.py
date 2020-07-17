import requests
import pendulum
import json
import re
from argparse import ArgumentParser


class GetBuildSecretsException(Exception):
    pass


parser = ArgumentParser(description="Checks a CircleCI project for signs of vulnerable configuration in regards to fork behaviour and secrets")
parser.add_argument("-p", "--project", help="project to request circleci build logs for, in the format of project/repo")
parser.add_argument("-c", "--circleci-token", help="The CircleCI API token for non public readable builds")
parser.add_argument("-g", "--github-token", help="The Github API token")
parser.add_argument("-i", "--ignore-users", help="Ignore specific Github users from the forked PR collection, comma separated")
parser.add_argument("-a", "--check-all", action="store_true", help="Go through all found CircleCI builds even if secret usage was already found")
parser.add_argument("-v", "--verbose", action="store_true", help="More output")

args = parser.parse_args()

if not args.project:
    print('Must supply a project value')
    exit(1)

project = args.project.split('/')[0]
repo = args.project.split('/')[1]
token = args.circleci_token
github_token = args.github_token
ignore_users = args.ignore_users
check_all_circleci_builds = args.check_all
verbose = args.verbose

print('Trying %s/%s...' % (project, repo))

# collect the 10 most recent PRs from forks for the Github repo
s_github = requests.session()
gh_headers = {}
if github_token:
    gh_headers['Authorization'] = 'token %s' % (github_token)
page = 1
gh_prs = []
while True:
    if verbose:
        print("Getting page %s for %s/%s PRs..." % (page, project, repo))
    res = s_github.get('https://api.github.com/repos/%s/%s/pulls' % (project, repo), headers=gh_headers, params={'page': page, 'state': 'all' })
    data = res.json()
    if len(data) > 0:
        for pr in data:
            pr_user = pr['user']['login'] if 'user' in pr and 'login' in pr['user'] else ''
            if pr_user and ignore_users and pr_user in ignore_users.split(','):
                if verbose:
                    print('Ignoring PR from %s' % (pr_user))
                continue
            if (
                pr and 'head' in pr and pr['head'] and 'repo' in pr['head'] and pr['head']['repo'] and 'sha' in pr['head'] and
                'fork' in pr['head']['repo'] and pr['head']['repo']['fork']
            ):
                # if the PR author is publicly known as a privileged user for this repo, skip
                if pr['author_association'] in ['OWNER', 'MEMBER']:
                    continue
                gh_prs.append(
                    {
                        'sha': pr['head']['sha'],
                        'number': pr['number'],
                        'user': pr['user']['login'] if 'user' in pr and 'login' in pr['user'] else '',
                        'merged_at': pr['merged_at'] if 'merged_at' in pr else None
                    }
                )
                if verbose:
                    print('Found PR %s (commit %s) from fork %s' % (pr['number'], pr['head']['sha'], pr['head']['repo']['full_name']))
                if len(gh_prs) >= 10:
                    break
    else:
        if verbose:
            print('Done collecting forked PRs')
        break
    if len(gh_prs) >= 10:
        if verbose:
            print('Done collecting forked PRs')
        break
    page += 1

if len(gh_prs) == 0:
    print('%s/%s: No builds found which came from a forked PR - unable to determine whether this project is vulnerable' % (project, repo))
    exit(1)

# collect the CircleCI build IDs from the Github statuses
if verbose:
    print('Collecting CircleCI build ids associated with the forked PRs...')
forked_builds = []
forked_builds_user_map = {}
for pr in gh_prs:
    res = s_github.get('https://api.github.com/repos/%s/%s/commits/%s/status' % (project, repo, pr['sha']), headers=gh_headers)
    data = res.json()
    if data and 'statuses' in data:
        for status in data['statuses']:
            if status and 'target_url' in status and status['target_url'] and '//circleci.com/' in status['target_url'].lower():
                build_num_matches = re.match(r'https:\/\/circleci\.com\/gh\/[^\/]+\/[^\/]+\/(\d+)', status['target_url'].lower())
                if build_num_matches:
                    build_num = int(build_num_matches.group(1))
                    if build_num not in forked_builds:
                        if (
                            pr['merged_at'] and 'created_at' in status and status['created_at'] and
                            pendulum.parse(pr['merged_at']) < pendulum.parse(status['created_at'])
                        ):
                            if verbose:
                                print('CircleCI build %s was created after the PR was merged' % (build_num))
                            continue
                        forked_builds.append(build_num)
                        # record the PR user, accoding to Github, for this CircleCI build number, for later comparison
                        forked_builds_user_map[build_num] = pr['user']
                        if verbose:
                            print('Found CircleCI build %s from PR %s (commit %s)' % (build_num, pr['number'], pr['sha']))

if len(forked_builds) == 0:
    print('%s/%s: No CircleCI statuses found - unlikely to be vulnerable' % (project, repo))
    exit(1)

forked_builds.sort(reverse=True)

if verbose:
    print('%s/%s has evidence of forked pull requests creating CircleCI builds' % (project, repo))

circleci_url = 'https://circleci.com/api/v1.1/project/github/%s/%s' % (project, repo)
s_circle = requests.session()

# collect the relevant logs of the supplied build number and look for evidence of secrets being available
def get_build_secret_names(build_num):
    if verbose:
        print('Checking build %s...' % (build_num))
    s3_file_url = ''

    found_prepare_env_var_action = False
    found_spin_up_env_action = False
    params = {}
    if token:
        params['circle-token'] = token
    r = s_circle.get('%s/%s' % (circleci_url, build_num), params=params)
    build_details = r.json()

    if 'user' in build_details and 'is_user' in build_details['user'] and build_details['user']['is_user'] and 'login' in build_details['user']:
        if forked_builds_user_map[build_num] != build_details['user']['login']:
            raise GetBuildSecretsException(
                'PR user is not the same as build user (Github PR: %s, CircleCI build: %s - this could indicate a privileged user/bot ran the build' %
                (forked_builds_user_map[build_num], build_details['user']['login'])
            )
    if 'branch' in build_details and build_details['branch'] and 'pull' not in build_details['branch'].lower():
        raise GetBuildSecretsException('This build was not a pull request branch, possibly caused by a merge and not by opening a PR')
    if 'steps' in build_details:
        for job, step in enumerate(build_details['steps']):
            if 'actions' in step and len(step['actions']) > 0:
                for a, action in enumerate(step['actions']):
                    if 'name' in action and action['name'] and 'preparing environment variables' in action['name'].lower():
                        if verbose:
                            print('Found "Preparing Environment Variables" job')
                        found_prepare_env_var_action = True
                        if 'output_url' in action:
                            s3_file_url = action['output_url']
                    if s3_file_url:
                        break
            if s3_file_url:
                break
        # try the legacy action if the current action with env vars wasn't found
        if not found_prepare_env_var_action:
            if verbose:
                print('Did not find a "Preparing Environment Variables" job, trying for "Spin up Environment" ...')
            for job, step in enumerate(build_details['steps']):
                if 'actions' in step and len(step['actions']) > 0:
                    for a, action in enumerate(step['actions']):
                        if 'name' in action and action['name'] and 'spin up environment' in action['name'].lower():
                            if verbose:
                                print('Found "Spin up Environment" job')
                            found_spin_up_env_action = True
                            if 'output_url' in action:
                                s3_file_url = action['output_url']
                        if s3_file_url:
                            break
                if s3_file_url:
                    break

    if not found_prepare_env_var_action and not found_spin_up_env_action:
        raise GetBuildSecretsException('%s/%s: Could not find an action showing environment variables used' % (project, repo))

    if not s3_file_url:
        raise GetBuildSecretsException('%s/%s: Failed to get S3 download URL for environment variable job output' % (project, repo))

    if verbose:
        print('Downloading job output for build %s ...' % (build_num))
    s_s3 = requests.session()
    dl = s_s3.get(s3_file_url)
    output = json.loads(dl.content.decode())
    message = output[0]['message'] if len(output) > 0 and 'message' in output[0] else ''
    if not message:
        raise GetBuildSecretsException('Job output download was empty')
    message = message.replace('\\n', "\n").replace('\\r', "")
    message_split = message.split('\n')

    # we only care about env vars listed under "Using environment variables from project settings and/or contexts" that are not "CIRCLE_JOB"
    try:
        if found_prepare_env_var_action:
            index = message_split.index('Using environment variables from project settings and/or contexts:')
        else:
            index = message_split.index('Using environment variables from project settings and/or contexts')
    except Exception as e:
        index = None

    if not index:
        raise GetBuildSecretsException(
            '%s/%s: Could not find the "Using environment variables from project settings and/or contexts:" message in the job output' % (project, repo)
        )

    envvars = message_split[index:]
    secrets = []
    for envvar in envvars:
        matches = re.match(r'([^ =]+)=\*\*REDACTED\*\*', envvar.strip())
        if matches:
            secret = matches.group(1)
            if verbose and secret:
                print('Found reference to env var "%s"' % secret)
            if secret and secret != 'CIRCLE_JOB':
                secrets.append(secret)
    return secrets

# go through the forked builds looking for usage of potentially sensitive secrets
first_try = False
secrets = []
for build_num in forked_builds:
    try:
        secrets += get_build_secret_names(build_num)
    except GetBuildSecretsException as e:
        if verbose:
            print(e)
    if len(secrets) > 0:
        if forked_builds.index(build_num) == 0:
            first_try = True
        if not check_all_circleci_builds:
            break

if len(secrets) == 0:
    print('%s/%s: Forked PRs do run builds, but no references to non-default secrets were found' % (project, repo))
    exit(1)

if first_try:
    print('%s/%s: may be vulnerable!' % (project, repo))
else:
    print('%s/%s: an older forked PR build task was passed secrets, may be vulnerable!' % (project, repo))
