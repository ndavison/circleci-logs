import requests
import json
import os
from argparse import ArgumentParser


parser = ArgumentParser(description="Checks a Github org for repos, or members of the org with personal repos, which have projects on CircleCI")
parser.add_argument("-o", "--org", help="Github org to check")
parser.add_argument("-t", "--token", help="Github token for authenticated API requests, used in the Authorization header")
parser.add_argument("-c", "--circle-token", help="CircleCI token for authenticated API requests")
parser.add_argument("-m", "--members-only", action="store_true", help="Collect the org members and their repos on CircleCI")
parser.add_argument("-v", "--verbose", action="store_true", help="More output")

args = parser.parse_args()

if not args.org:
    print('Must supply a org value')
    exit(1)

org = args.org
members_only = args.members_only
verbose = args.verbose
token = args.token
circle_token = args.circle_token

github_repos = []
headers = {}
if token:
    headers['Authorization'] = 'token %s' % (token)

s_github = requests.session()

# collect all the relevant Github org/member and repo pairs
if not members_only:
    has_repos = True
    page = 1
    while has_repos:
        if verbose:
            print('Getting repos in %s...' % (org))
        data = []
        try:
            res = s_github.get('https://api.github.com/orgs/%s/repos' % (org), headers=headers, params={'page': page })
            data = res.json()
        except requests.exceptions.ConnectionError as e:
            continue
        if len(data) > 0:
            for repo in data:
                if 'name' in repo:
                    github_repos.append({'org': org, 'repo': repo['name']})
                    if verbose:
                        print('Found repo %s' % (repo['name']))
        else:
            has_repos = False
            if verbose:
                print('Done collecting org repos')
        page += 1
    if len(github_repos) == 0 and verbose:
        print('No repos found in %s...' % (org))
else:
    members = []
    has_members = True
    page = 1
    while has_members:
        if verbose:
            print('Getting members in %s...' % (org))
        data = []
        try:
            res = s_github.get('https://api.github.com/orgs/%s/members' % (org), headers=headers, params={'page': page })
            data = res.json()
        except requests.exceptions.ConnectionError as e:
            continue
        if len(data) > 0:
            for repo in data:
                if 'login' in repo:
                    members.append(repo['login'])
                    if verbose:
                        print('Found member %s' % (repo['login']))
        else:
            has_members = False
            if verbose:
                print('Done collecting members')
        page += 1
    if len(members) == 0 and verbose:
        print('No members found in %s...' % (org))
    
    for member in members:
        has_repos = True
        page = 1
        while has_repos:
            if verbose:
                print('Getting repos in member %s...' % (member))
            data = []
            try:
                res = s_github.get('https://api.github.com/users/%s/repos' % (member), headers=headers, params={'page': page })
                data = res.json()
            except requests.exceptions.ConnectionError as e:
                continue
            if len(data) > 0:
                for repo in data:
                    if 'name' in repo:
                        github_repos.append({'org': member, 'repo': repo['name']})
                        if verbose:
                            print('Found repo %s for member %s' % (repo['name'], member))
            else:
                has_repos = False
                if verbose:
                    print('Done collecting member repos')
            page += 1
        if len(github_repos) == 0 and verbose:
            print('No repos found in member %s...' % (member))

# check the repos for a CircleCI project
circle_projects = []
s_circle = requests.session()
params = {'limit': 1}
if circle_token:
	params['circle-token'] = circle_token
if verbose:
    print('Trying to collect CircleCI projects...')
for pair in github_repos:
    if verbose:
        print('Trying %s' % (pair['repo']))
    url = 'https://circleci.com/api/v1.1/project/github/%s/%s' % (pair['org'], pair['repo'])
    res = s_circle.get(url, params=params)
    if res.status_code != 404:
        data = res.json()
        if len(data) > 0:
            circle_projects.append(pair)
            if verbose:
                print('Found %s/%s' % (pair['org'], pair['repo']))

if len(circle_projects) == 0 and verbose:
    print('No CircleCI projects found')

for pair in circle_projects:
    print('%s/%s' % (pair['org'], pair['repo']))
