#!/usr/bin/env python3
# MOD Cloud Builder
# SPDX-FileCopyrightText: 2023 MOD Audio UG
# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import json

from asyncio.subprocess import create_subprocess_shell, PIPE, STDOUT
from tempfile import TemporaryDirectory
from tornado.ioloop import IOLoop
from tornado.web import Application, HTTPError, RequestHandler
from tornado.websocket import WebSocketHandler

BUILDER_PACKAGE_DIR = './plugins/package'
TARGET_PLATFORM = 'moddwarf-new'

class Builder(object):
    active = {}

    def __init__(self, pkgbundle):
        self.pkgbundle = pkgbundle

        self.projdir = TemporaryDirectory(dir=BUILDER_PACKAGE_DIR)
        self.projname = os.path.basename(self.projdir.name)

        self.proc = None

    async def build(self, write_message_callback):
        print("Builder.build", write_message_callback)
        os.environ['BUILDER_TARGET_DIR'] = self.projdir.name
        self.proc = await create_subprocess_shell(f'./build {TARGET_PLATFORM} {self.projname}', stdout=PIPE, stderr=STDOUT)
        while self.proc is not None:
            stdout = await self.proc.stdout.readline()
            if self.proc is None:
                break
            if stdout == b'':
                self.proc = None
                # self.write_message(u"Build completed successfully, fetching plugin binaries...")
                # self.write_message(u'--- BINARY ---')
                # IOLoop.instance().add_callback(self.plugin_package)
                break
            write_message_callback(stdout)

    def destroy(self):
        Builder.active.pop(self.projname)

        if self.proc is not None:
            proc = self.proc
            self.proc = None
            proc.kill()

        self.projdir.cleanup()

    @classmethod
    def create(kls, pkgbundle):
        builder = Builder(pkgbundle)
        kls.active[builder.projname] = builder
        return builder

    @classmethod
    def get(kls, projname):
        return kls.active[projname]

class BuilderRequest(RequestHandler):
    def prepare(self):
        if 'application/json' in self.request.headers.get('Content-Type'):
            self.jsonrequest = json.loads(self.request.body.decode('utf-8'))
        else:
            raise HTTPError(501, 'Content-Type != "application/json"')

    def done(self, data):
        self.set_header('Content-Type', 'application/json; charset=UTF-8')
        self.write(json.dumps(data))
        self.finish()

    def post(self):
        # validate package contents
        package = self.jsonrequest.get('package', None)
        if package is None:
            self.done({ 'ok': False, 'error': "Missing package" })
            return

        if '$(BUILDER_TARGET_DIR)' not in package:
            self.done({ 'ok': False, 'error': "Missing special handling for builder target dir" })
            return

        files = self.jsonrequest.get('files', None)
        if not files:
            self.done({ 'ok': False, 'error': "Missing files" })
            return

        # get package name
        pkgname = package.split('_VERSION = ',1)[0].split('\n',1)[-1].split('#',1)[0]
        if not pkgname or not pkgname.replace('_','').isalnum() or pkgname[0].isdigit():
            self.done({ 'ok': False, 'error': "Invalid package version" })
            return

        # get package bundle
        pkgbundle = package.split('_BUNDLES = ',1)[1].split('\n',1)[0].split('#',1)[0].strip()
        if not pkgbundle:
            self.done({ 'ok': False, 'error': "Invalid package bundle name" })
            return
        if ' ' in pkgbundle:
            self.done({ 'ok': False, 'error': "Multiple bundles per package is not supported" })
            return

        # prepare for build
        builder = Builder.create(pkgbundle)

        # create plugin files
        with open(os.path.join(BUILDER_PACKAGE_DIR, builder.projname, builder.projname + '.mk'), 'w') as fh:
            fh.write(package.replace(f'{pkgname}_', f'{builder.projname.upper()}_'))

        for f in files:
            with open(os.path.join(BUILDER_PACKAGE_DIR, builder.projname, f['filename']), 'w') as fh:
                fh.write(f['content'])

        self.done({ 'ok': True, 'id': builder.projname })

    def get(self):
        package = self.get_argument('id')
        # TODO
        # 1: return packed binary
        return

class BuilderWebSocket(WebSocketHandler):
    # async def plugin_package(self):
    #     # FIXME randomize bundle name?
    #     self.proc = await create_subprocess_shell(f'tar -C ~/mod-workdir/moddwarf-new/plugins -chz midi-display.lv2 -O', stdout=PIPE)
    #     while self.proc is not None:
    #         stdout = await self.proc.stdout.read(8192)
    #         if self.proc is None:
    #             break
    #         if stdout == b'':
    #             self.proc = None
    #             self.close()
    #             break
    #         self.write_message(stdout, True)
    # 
    # async def plugin_build(self):
    #     self.proc = await create_subprocess_shell(f'./build moddwarf-new {self.projname}', stdout=PIPE, stderr=STDOUT)
    #     while self.proc is not None:
    #         stdout = await self.proc.stdout.readline()
    #         if self.proc is None:
    #             break
    #         if stdout == b'':
    #             self.proc = None
    #             self.write_message(u"Build completed successfully, fetching plugin binaries...")
    #             self.write_message(u'--- BINARY ---')
    #             IOLoop.instance().add_callback(self.plugin_package)
    #             break
    #         self.write_message(stdout)

    async def build(self):
        print("BuilderWebSocket.build")
        await self.builder.build(self.write_message)

    def open(self):
        print("BuilderWebSocket.open")
        # WebSocketHandler.open(self)
        self.builder = None
    
    # def close(self):
    #     WebSocketHandler.close(self)
    #     self.builder = None

    def on_message(self, message):
        # if self.proc is not None:
        #     self.write_message(u"Build already active, cannot trigger a 2nd one on the same socket")
        #     self.close()
        #     return
        # 
        # message = message.strip()
        # versionline = message.split('\n',1)[0].split('#',1)[0]
        # versionpkg = versionline.split('_VERSION',1)[0]
        # if not versionpkg or ' ' in versionpkg:
        #     self.write_message(u"Invalid package")
        #     self.close()
        #     return
        # 
        # self.projdir = TemporaryDirectory(dir='./plugins/package')
        # self.projname = os.path.basename(self.projdir.name)
        # 
        # with open(os.path.join(self.projdir.name, self.projname + '.mk'), 'w') as fh:
        #     fh.write(message.replace(versionpkg+'_',self.projname.upper()+'_'))

        # self.write_message(u"Starting build for "+versionpkg.lower()+'...')

        if not message.isalnum():
            self.close()
            return

        self.builder = Builder.get(message)
        IOLoop.instance().add_callback(self.build)

    def on_close(self):
        print("BuilderWebSocket.on_close")
        if self.builder is None:
            return
        self.builder.destroy()

        # proc = self.proc
        # projdir = self.projdir
        # self.proc = self.projname = self.projdir = None
        # proc.kill()
        # projdir.cleanup()

    def check_origin(self, origin):
        return True

if __name__ == "__main__":
    print ("Starting using port 8000...")
    app = Application([
        (r'/', BuilderRequest),
        (r'/build', BuilderWebSocket)
    ])
    app.listen(8000)
    IOLoop.instance().start()
