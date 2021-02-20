#!/usr/local/bin/python
# -*- coding: utf-8 -*-
import json
import requests
import argparse
import sys
import os
import configparser
import getpass
from builtins import input
from git import Repo, GitCommandError, InvalidGitRepositoryError
from prettytable import PrettyTable

config_dir = os.path.expanduser("~") + "/.config/relm"
cfg_path = os.path.join(config_dir, "relm.ini")
cur_dir = os.getcwd()
config = None
repo = None


def load_config(recreate=False):
    _config = configparser.ConfigParser()
    try:
        with open(cfg_path) as source:
            _config.read_file(source)
    except IOError:
        print("file %s not found" % cfg_path)

    if recreate:
        os.remove(cfg_path)

    cfg = {}
    _reload = False
    try:
        cfg['JiraUrl'] = _config['DEFAULT']['JiraUrl']
    except KeyError:
        _config['DEFAULT']['JiraUrl'] = input("Jira URL: ")
        _reload = True

    try:
        cfg['JiraAuth'] = _config['DEFAULT']['JiraAuth']
    except KeyError:
        jira_user = input("Jira user: ")
        jira_pass = getpass.getpass("Jira password: ")
        import base64
        _config['DEFAULT']['JiraAuth'] = base64.b64encode("{0}:{1}".format(jira_user, jira_pass)
                                                          .encode()).decode("utf-8")
        _reload = True

    try:
        cfg['JiraProject'] = _config[cur_dir]['JiraProject']
    except KeyError:
        _config[cur_dir] = {}
        _config[cur_dir]['JiraProject'] = input("Jira proj: ")
        _reload = True

    if _reload:
        if not os.path.exists(config_dir):
            os.makedirs(config_dir)
        with open(cfg_path, 'w') as configfile:
            _config.write(configfile)
        cfg = load_config()

    return cfg


class Jira(object):
    """"""

    def __init__(self):
        self._cfg = config
        self._url = "%s/rest/api/latest/search" % self._cfg['JiraUrl']
        self._project = self._cfg['JiraProject']
        self._headers = {
            'authorization': 'Basic %s' % self._cfg['JiraAuth'],
            'content-type': "application/json"
        }

    def _issues(self, payload):
        _data = json.dumps(payload)
        _r = requests.post(self._url, data=_data, headers=self._headers)
        if _r.status_code != 200:
            print("jira: access denied")
            exit(2)
        if 'errorMessages' in _r:
            for m in _r['errorMessages']:
                print(m)
            return None

        return _r.json()['issues']

    def get_issues_keys(self, release_name):
        jira_statuses = '"Tested In Branch"'
        if not release_name:
            jira_statuses += ',"Ready For QA","In Testing"'

        not_labels = '"wait"'

        additional_param = 'and fixVersion is EMPTY' if not release_name else ""

        payload = {"jql": "project = {0} \
                   and status in ({1}) \
                   and (labels not in ({2}) or labels is EMPTY) {3}".format(self._project, jira_statuses,
                                                                            not_labels,
                                                                            additional_param),
                   "fields": ["key"]}
        response = self._issues(payload)
        issues = [issue['key'] for issue in response]
        return issues

    def get_issue_status_by_key(self, keys):
        if type(keys) is not str:
            keys = ",".join(keys)
        payload = {"jql": "project = {0} \
                               and issuekey in ({1})".format(self._project,
                                                             keys),
                   "fields": ["status"]}
        response = self._issues(payload)
        if response is None:
            print("No issues founded")
            return
        issues = [{'key': issue['key'], 'status': issue['fields']
        ['status']['name']} for issue in response]
        return sorted(issues, key=lambda k: k['status'])


def contain_in_branches(commit_hash):
    return repo.git.branch("-r", "--contains", "%s" % commit_hash.strip()) \
        .replace(" ", ""). \
        replace("origin/", "") \
        .split('\n')


def get_branches():
    if repo.remotes:
        branches_list = [{'key': t.name[7:], 'updated': t.commit.authored_datetime}
                         for t in repo.remotes[0].refs]
        return branches_list
    else:
        raise Exception("Remote repo not exist")


def get_and_merge(br_name, release):
    delete = True

    if br_name not in repo.branches:
        remote_branch = repo.remotes[0].refs[br_name]
        local_branch = repo.create_head(br_name, remote_branch)
        local_branch.set_tracking_branch(remote_branch)
    else:
        local_branch = repo.branches[br_name]
        local_branch.checkout()
        repo.remotes[0].pull()

    if release:
        release.checkout()
        try:
            m = repo.git.execute(["git", "merge", "--no-edit", br_name])
            if m not in "'Already up-to-date.":
                m = "merged"
            print("{0} {1}".format(br_name, m))
        except GitCommandError:
            print("%s conflict" % br_name)
            repo.head.reset(working_tree=True)
            delete = False
    else:
        local_branch.checkout()
        try:
            m = repo.git.execute(["git", "merge", "--no-edit", 'master'])
            if m not in "'Already up-to-date.":
                m = "merged"
                delete = False
            print("{0} {1}".format(br_name, m))
        except GitCommandError:
            print("%s conflict" % br_name)
            repo.git.execute(["git", "merge", "--abort"])
            delete = False

    repo.heads.master.checkout()
    if delete:
        repo.delete_head(br_name, force=True)


def run(args, jira):
    release_name = args.release
    issues = args.issues if args.issues else jira.get_issues_keys(release_name)

    if release_name:
        print("---merge to %s---" % release_name)
        repo.heads.master.checkout()
        if release_name not in repo.branches:
            if release_name not in repo.remotes[0].refs:
                release = repo.create_head(release_name)
            else:
                remote_release = repo.remotes[0].refs[release_name]
                release = repo.create_head(release_name, remote_release)
                release.set_tracking_branch(remote_release)
        else:
            release = repo.heads[release_name]
    else:
        print("---merge from master---")
        release = None

    _branches = get_branches()
    branch_name = [t['key'] for t in _branches]

    exists = set(branch_name) & set(issues)
    for b in exists:
        get_and_merge(b, release)

    not_exists = set(issues) - set(branch_name)
    print('---issues with branches not found---')
    all_commits = repo.git.log(["--all", "--oneline"]).split('\n')
    for issue in not_exists:
        branches = [contain_in_branches(com[:8])
                    for com in all_commits if issue in com]
        uniq_branches = set(sum(branches, []))
        msg = "{0} belong to {1}".format(issue, uniq_branches)
        print(msg)


def main():
    parser = argparse.ArgumentParser(description="Release Management Tool")
    parser.add_argument(
        "-r", "--release", help="set release name")
    parser.add_argument("-i", "--issues", nargs='*',
                        help="set issues manually")
    parser.add_argument("-s", "--status", action='store_true',
                        help="check issues statuses for branch")
    parser.add_argument(
        "-m", "--merge", action='store_true', help="merge from master")
    parser.add_argument('--version', action='version', version='%(prog)s 0.0.1.1')
    args = parser.parse_args()

    global config
    global repo

    try:
        config = load_config()
        repo = Repo(cur_dir)
        jira = Jira()

        if args.status:
            branches = get_branches()
            issues = jira.get_issue_status_by_key([t['key'] for t in branches])
            t = PrettyTable(['key', 'status', 'commit'])
            if issues:
                for i in issues:
                    i['commit'] = [k['updated'] for k in branches if i['key'] in k['key']][0]
                    t.add_row([i['key'], i['status'], i['commit'].strftime('%Y-%m-%d')])
                print(t)

        elif args.release or args.merge:
            run(args, jira)

        else:
            parser.print_help()
    except KeyboardInterrupt:
        print("exit")
        sys.exit(1)
    except InvalidGitRepositoryError:
        print("WARN: in current directory git not found")
        print("exit")
        sys.exit(2)


if __name__ == '__main__':
    main()
