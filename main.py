#!/usr/bin/env python

import requests
import yaml
import argparse
import re

class ComparisonException(RuntimeError):
    pass

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
                    parent = parent | match
                    item = parent
                except KeyError:
                    # has no parent
                    pass
                return item
        return RuntimeError(f'no item "{key}" found')

    def string_vars_replace(self, string, variables=None):
        if variables is None:
            variables = self.variables
        vars = re.findall('\\{[^}]+\\}', string)
        for var in vars:
            # cut off brackets
            key = var[1:-1]
            # cut off leading and trailing spaces
            key = key.strip()
            try:
                value = self.variables[key]
            except KeyError:
                raise KeyError(f'variable "{key}" not defined')
            string = string.replace(var, value)
        return string

    def vars_replace(self, subject, variables=None):
        if type(subject) is dict:
            subject = subject.copy()
            for key, value in subject.items():
                subject[key] = self.vars_replace(value)
        elif type(subject) is list:
            subject = list(map(self.vars_replace, subject))
        elif type(subject) in [str, int, float, bool]:
            return self.string_vars_replace(str(subject))

        return subject 

    def find_request(self, key: str):
        return self.find_item(self.requests, key)

    def find_test(self, key: str):
        return self.find_item(self.tests, key)

    def send_request(self, request):
        method = request.get('method', 'GET')
        url = request['url']
        payload = request.get('payload')
        headers = request.get('headers', [])
        headers = map(lambda header: (header['key'], header['value']), headers)
        headers = dict(headers)

        response = requests.request(
            method=method,
            url=url,
            json=payload,
            headers=headers
        )

        result = {
            'http_code': response.status_code,
            'text': response.text,
            'json': {}
        }

        try:
            result['json'] = response.json()
        except:
            pass

        return result

    def ensure_list(self, item):
        if type(item) is list:
            return item
        return [item]

    def print_color(self, text, color):
        colors = {
            'fail': '\033[91m',
            'ok': '\033[92m',
            'end': '\033[0m'
        }
        print(f'{colors[color]}{text}{colors["end"]}', end='')

    def print_fail(self, text):
        self.print_color(text, 'fail')

    def print_ok(self, text):
        self.print_color(text, 'ok')

    def print_label_fail(self, text):
        print('[', end='')
        self.print_fail('FAIL')
        print(f'] {text}')

    def print_label_ok(self, text):
        print('[', end='')
        self.print_ok('SUCCESS')
        print(f'] {text}')

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

    def dict_get_replaced(self, subject, key, additional_variables={}, default=None):
        result = subject.get(key)
        if result is None:
            return default
        return self.vars_replace(result, self.variables | additional_variables)

    def run_test(self, test: str|dict, name: None):
        if type(test) == str:
            test = self.find_test(test)

        print(f'running test {name}')

        self.run_commands(self.dict_get_replaced(test, 'before'))
        request = self.dict_get_replaced(test, 'request')
        if request is None:
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
        
        expect = self.dict_get_replaced(test, 'expect', response, default={})
        # default value
        expect = {'http_code': 200} | expect

        try:
            self.compare_recursive(expect, response, 'expect')
            self.print_label_ok(f'Test {name}')
        except ComparisonException as e:
            self.print_label_fail(e)
            self.print_label_fail(f'Test {name}')

        self.run_commands(self.dict_get_replaced(test, 'after', response))

    def run_all_tests(self):
        try:
            for i in range(len(self.tests)):
                test = self.tests[i]
                name = self.dict_get_replaced(test, 'name', default=f'Test #{i+1}')
                self.run_test(test, name)
        except Exception as e:
            self.print_label_fail(f'Error running test "{name}": {e}')

    def compare_recursive(self, expected, actual, path):
        if type(expected) is dict:
            for key in expected.keys():
                try:
                    self.compare_recursive(expected[key], actual[key], f'{path}.{key}')
                except KeyError:
                    raise ComparisonException(f'Value {path}.{key} not existant')
            return        

        if str(expected) != str(actual):
            raise ComparisonException(f'Unfulfiled comparison at {path} (expected: {expected}, actual: {actual})')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('-c', '--config', required=True, type=str, help='Path to test config file')
    parser.add_argument('-d', '--define', required=False, type=str, help='Initial variable definition', nargs='+', default=[])

    args = parser.parse_args()

    env = {}

    for define in args.define:
        # plit into key=value
        key = define[:define.find('=')]
        value = define[define.find('=') + 1:]
        env[key] = value

    file = args.config

    with open(file, 'r') as file:
        config = yaml.load(file, Loader=yaml.FullLoader)
    
    runner = TestRunner(config, env)

    runner.run_all_tests()

if __name__ == '__main__':
    main()