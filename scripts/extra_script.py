from os.path import join, isfile, basename
from os import listdir
import json
from pprint import pprint
import re


from css_html_js_minify.html_minifier import html_minify
#from css_html_js_minify.css_minifier import css_minify
#from css_html_js_minify.js_minifier import js_minify

Import("env")

#
# Dump build environment (for debug)
#print env.Dump()
#print("Current build targets", map(str, BUILD_TARGETS))
#

import httplib, urllib, sys

def js_minify(original):
    params = urllib.urlencode([
        ('js_code', original),
        ('compilation_level', 'SIMPLE_OPTIMIZATIONS'),
        ('output_format', 'text'),
        ('output_info', 'compiled_code'),
    ])

    # Always use the following value for the Content-type header.
    headers = {"Content-type": "application/x-www-form-urlencoded"}
    conn = httplib.HTTPConnection('closure-compiler.appspot.com')
    conn.request('POST', '/compile', params, headers)
    response = conn.getresponse()
    data = response.read()
    conn.close()
    return data

import requests

def css_minify(original, wrap=False, comments=False, sort=True):
    url = 'https://cssminifier.com/raw'
    data = {'input': original }
    response = requests.post(url, data=data)

    return response.text

def minify(env, target, source):
    output = ""
    for source_file in source:
        #print("Reading {}".format(source_file))
        file = source_file.get_abspath()
        with open(file) as source_fh:
            original = source_fh.read().decode('utf-8')
        if file.endswith(".css"):
            output += css_minify(original, wrap=False, comments=False, sort=True)
        elif file.endswith(".js"):
            output += js_minify(original)
            #output += original
        elif file.endswith(".htm") or file.endswith(".html"):
            output += html_minify(original, comments=False)
    target_file = target[0].get_abspath()
    print("Generating {}".format(target_file))
    with open(target_file, "w") as output_file:
        output_file.write(output.encode('utf-8'))

def get_c_name(source_file):
    return basename(source_file).upper().replace('.', '_').replace('-', '_')

def text_to_header(source_file):
    with open(source_file) as source_fh:
        original = source_fh.read().decode('utf-8')
    filename = get_c_name(source_file)
    output = "static const char CONTENT_{}[] PROGMEM = ".format(filename)
    for line in original.splitlines():
        output += "\n  \"{}\\n\"".format(line.replace('\\', '\\\\').replace('"', '\\"'))
    output += ";\n"
    return output

def binary_to_header(source_file):
    filename = get_c_name(source_file)
    output = "static const char CONTENT_"+filename+"[] PROGMEM = {\n  "
    count = 0

    with open(source_file, "rb") as source_fh:
        byte = source_fh.read(1)
        while byte != "":
            output += "0x{:02x}, ".format(ord(byte))
            count += 1
            if 16 == count:
                output += "\n  "
                count = 0

            byte = source_fh.read(1)

    output += "0x00 };\n"
    return output

def data_to_header(env, target, source):
    output = ""
    for source_file in source:
        #print("Reading {}".format(source_file))
        file = source_file.get_abspath()
        if file.endswith(".css") or file.endswith(".js") or file.endswith(".htm") or file.endswith(".html"):
            output += text_to_header(file)
        else:
            output += binary_to_header(file)
    target_file = target[0].get_abspath()
    print("Generating {}".format(target_file))
    with open(target_file, "w") as output_file:
        output_file.write(output.encode('utf-8'))

def make_static(env, target, source):
    output = ""

    # Load the manifest file
    manifest = source[0].get_abspath()
    with open(manifest) as manifest_file:
        man = json.load(manifest_file)

    out_files = []
    for out_file in man:
        out_files.append(out_file)
    for file in listdir(data_src):
        if isfile(join(data_src, file)) and not file in out_files:
          out_files.append(file)

    # include the files
    for out_file in out_files:
        filename = "web_server."+out_file+".h"
        output += "#include \"{}\"\n".format(filename)

    output += "StaticFile staticFiles[] = {\n"

    for out_file in out_files:
        filetype = "TEXT"
        if out_file.endswith(".css"):
            filetype = "CSS"
        elif out_file.endswith(".js"):
            filetype = "JS"
        elif out_file.endswith(".htm") or out_file.endswith(".html"):
            filetype = "HTML"
        elif out_file.endswith(".jpg"):
            filetype = "JPEG"
        elif out_file.endswith(".png"):
            filetype = "PNG"

        c_name = get_c_name(out_file)
        output += "  { \"/"+out_file+"\", CONTENT_"+c_name+", sizeof(CONTENT_"+c_name+") - 1, _CONTENT_TYPE_"+filetype+" },\n"

    output += "};\n"

    target_file = target[0].get_abspath()
    print("Generating {}".format(target_file))
    with open(target_file, "w") as output_file:
        output_file.write(output.encode('utf-8'))

def process_app_file(source_dir, source_files, data_dir, out_file, env):
    source = []
    for file in source_files:
        source.append(join(source_dir, file))
    data_file = join(data_dir, out_file)
    header_file = join("$PROJECTSRC_DIR", "web_server."+out_file+".h")
    env.Depends(header_file, env.Command(data_file, source, minify))
    #env.Depends("$PROJECTSRC_DIR/web_server.cpp", env.Command(header_file, data_file, data_to_header))
    env.Depends("$BUILDSRC_DIR/web_server_static.o", env.Command(header_file, data_file, data_to_header))

def process_html_app(source, dest, env):
    manifest = join(source, "manifest.json")
    out_files = []
    if isfile(manifest):
        with open(manifest) as manifest_file:
            man = json.load(manifest_file)
        for out_file in man:
            in_files = man[out_file]
            out_files.append(out_file)
            process_app_file(source, in_files, dest, out_file, env)
    for file in listdir(dest):
        if isfile(join(dest, file)) and not file in out_files:
            data_file = join(dest, file)
            header_file = join("$PROJECTSRC_DIR", "web_server."+file+".h")
            env.Depends("$BUILDSRC_DIR/web_server.o", env.Command(header_file, data_file, data_to_header))

    header_file = join("$PROJECTSRC_DIR", "web_server_static_files.h")
    env.Depends("$BUILDSRC_DIR/web_server_static.o", env.Command(header_file, manifest, make_static))

#
# Generate Web app resources
#
html_src = join(env.subst("$PROJECTSRC_DIR"), "html")
data_src = join(env.subst("$PROJECTSRC_DIR"), "data")
process_html_app(html_src, data_src, env)
