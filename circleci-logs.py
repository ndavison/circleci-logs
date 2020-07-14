import requests
import json
import os
from argparse import ArgumentParser


parser = ArgumentParser(description="Downloads build logs from circleci for a particular project and repo.")
parser.add_argument("-p", "--project", help="project and repo to request circleci build logs for, in the format of project/repo")
parser.add_argument("-t", "--token", default=None, help="API token for non public readable builds")

args = parser.parse_args()

if not args.project:
    print('Must supply a project value')
    exit(1)

if '/' not in args.project:
    print('Project must be in the format project/repo')
    exit(1)

project = args.project.split('/')[0]
repo = args.project.split('/')[1]
token = args.token
outfiles = 'out/circleci/{}/{}'.format(project, repo)

if not repo:
    print('Could not determine repo value')
    exit(1)

url = 'https://circleci.com/api/v1.1/project/github/{}/{}'.format(project, repo)

params = {}
if token:
    params['circle-token'] = token

s_circle = requests.session()
r = s_circle.get(url, params=params)

if not r.status_code == 200:
    print('API request failed with code: {}'.format(r.status_code))
    exit(1)

try:
    os.makedirs(outfiles)
except FileExistsError as e:
    pass

builds = r.json()

latest = builds[0]['build_num']
i = latest
s_s3 = requests.session()
while i > 0:
    if os.path.exists('{}/{}'.format(outfiles, i)):
        print('Skipping build {} ...'.format(i))
    else:
        os.mkdir('{}/{}'.format(outfiles, i))
        print('Checking {}/{} ...'.format(url, i))
        r_2 = s_circle.get('{}/{}'.format(url, i), params=params)
        build_details = r_2.json()
        if 'steps' in build_details:
            for job, step in enumerate(build_details['steps']):
                if 'actions' in step and len(step['actions']) > 0:
                    for a, action in enumerate(step['actions']):
                        if 'output_url' in action:
                            print('Downloading {} ...'.format(action['output_url']))
                            dl = s_s3.get(action['output_url'])
                            filename = '{}/{}/job-{}-{}'.format(outfiles, i, job, a)
                            content = dl.content.decode().replace('\\n', "\n")
                            content = content.replace('\\r', "\r")
                            open(filename, 'w').write(content)
    i -= 1
