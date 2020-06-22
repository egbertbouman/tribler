import os
import binascii
from base64 import b64decode
from mimetypes import guess_type

from aiohttp import web

from tribler_core.restapi.rest_endpoint import RESTEndpoint
from tribler_core.utilities import path_util


class DebugUIEndpoint(RESTEndpoint):
    """
    This endpoint is responsible for returning index.html used by the debug web ui.
    """

    def setup_routes(self):
        self.app.add_routes([web.get('/{path:.*}', self.get_file)])

    async def get_file(self, request):
        filename = request.match_info.get('path') or 'index.html'
        response = web.FileResponse(path_util.Path(os.path.dirname(__file__)) / 'debug-ui' / filename)
        response.content_type = guess_type(filename)[0]
        return response

    @staticmethod
    def extract_api_key_from_auth(request):
        api_key = None
        if 'Authorization' in request.headers and request.headers['Authorization'].startswith('Basic '):
            try:
                credentials = b64decode(request.headers['Authorization'].split()[1]).decode()
            except binascii.Error:
                pass
            else:
                if ':' in credentials:
                    api_key = credentials.split(':')[1]
        return api_key
