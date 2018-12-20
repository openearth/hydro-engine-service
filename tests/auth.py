import os
import base64

# if 'privatekey.json' is defined in environmental variable - write it to file
if 'key' in os.environ:
    print('Writing privatekey.json from environmental variable ...')
    content = base64.b64decode(os.environ['key']).decode('ascii')

    with open('../privatekey.json', 'w') as f:
        f.write(content)

os.environ['key_path'] = '../privatekey.json'
