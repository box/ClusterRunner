# This script hits shutdown endpoint on ClusterRunner master for given node id.

import aiohttp
import asyncio
import hmac
import json
import sys
import traceback
import urllib.parse

if len(sys.argv) < 3:
    print('Must specify CR master url, clusterrunner.yaml file path and at least one slave id')
    sys.exit(1)
master = sys.argv[1]
config_path = sys.argv[2]
slave_ids = list(map(int, sys.argv[3:]))

with open(config_path, 'r') as f:
    lines = map(str.strip, f.readlines())
    key_vals = (map(str.strip, line.split('=', 2)) for line in lines
                if '=' in line)
    secret = next((val for key, val in key_vals if key == 'secret'), None)

if secret is None:
    print('Could not find secret in {}'.format(config_path))
    sys.exit(1)

async def shutdown_slave(session: aiohttp.ClientSession, slave_id: int):
    url = urllib.parse.urljoin(master, '/v1/slave/' + str(slave_id)) + '/shutdown'
    digest = hmac.new(
            secret.encode('utf-8'),
            digestmod='sha512').hexdigest()
    headers = {'Clusterrunner-Message-Authentication-Digest': digest}

    result = await session.post(url, headers=headers)
    result.raise_for_status()
    return result


async def main():
    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(
            *(shutdown_slave(session, slave_id) for slave_id in slave_ids),
            return_exceptions=True)
        for slave_id, result in zip(slave_ids, results):
            if isinstance(result, Exception):
                print('Could not shutdown slave id {}'.format(slave_id))
                traceback.print_exception(type(result), result, result.__traceback__)
            else:
                print('Shutdowned slave id {}'.format(slave_id))

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
