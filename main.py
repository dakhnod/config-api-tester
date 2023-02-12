#!/usr/bin/env python

import requests
import yaml
import argparse

class TestRunner():
    def __init__(self, config, variables={}) -> None:
        self.requests = config.get('requests', [])
        self.tests = config.get('tests', [])
        self.variables = variables

    def find_item(self, haystack: list, key: str):
        for item in haystack:
            if item['name'] == key:
                match = item

                try:
                    parent = self.find_item(match['inherit'])
                    parent = parent.copy()
                    parent.update(match)
                    item = parent
                except KeyError:
                    # has no parent
                    pass
                return item
        return RuntimeError(f'no item "{key}" found')

    def find_request(self, key: str):
        return self.find_item(self.requests, key)

    def find_test(self, key: str):
        return self.find_item(self.tests, key)

    def send_request(self, request):
        method = request.get('method', 'GET')
        url = request['url']
        payload = request.get('payload')
        headers_list = request.get('headers', [])
        # headers = map(lambda header: (header['key'], header['value']), headers_list)

        response = requests.request(
            method=method,
            url=url,
            json=payload,
            # headers=headers
        )

        return {
            'http_code': response.status_code
        }

    def ensure_list(item):
        if type(item) is list:
            return item
        return [item]

    def run_set(self, set: list|dict):
        set = self.ensure_list(set)
        for command in set:
            self.variables[command['key']] = command['value']


    def run_commands(self, commands: dict):
        if commands is None:
            return
        for key, handler in {
            'set': 'run_set'
        }.items():
            try:
                self.__getattribute__(handler)(commands[key])
            except KeyError:
                pass

    def run_test(self, test: str|dict):
        if type(test) == str:
            test = self.find_test(test)

        print(f'running test {test["name"]}')

        self.run_commands(test.get('before'))
        try:
            request = test['request']
        except KeyError:
            # no request defined
            return
        if type(request) == 'str':
            request = self.find_request(request)
        elif type(request) == dict:
            # nothing to do
            pass
        else:
            raise RuntimeError('unknown request type')

        response = self.send_request(request)
        
        success = True
        expect = test.get('expect', {})
        try:
            expect['http_code']
        except KeyError:
            # default http code
            expect['http_code'] = 200
        for key, value in expect.items():
            if response[key] != value:
                success = False
                print(f'key {key} not matching')

        self.run_commands(test.get('after'))

    def run_all_tests(self):
        for test in self.tests:
            self.run_test(test)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True, type=str, help='Path to test config file')

    args = parser.parse_args()

    file = args.config

    with open(file, 'r') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)
    
    runner = TestRunner(config)
    runner.run_all_tests()

if __name__ == '__main__':
    main()