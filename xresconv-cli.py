#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
import os, platform, locale
import shutil, re, string
import xml.etree.ElementTree as ET
import glob, getopt
from multiprocessing import cpu_count
from print_color import print_style, cprintf_stdout, cprintf_stderr
from optparse import OptionParser

console_encoding = sys.getfilesystemencoding()

if 'utf-8' != sys.getdefaultencoding().lower():
    try:
        sys.setdefaultencoding('utf-8')
    except Exception:
        reload(sys)
        sys.setdefaultencoding('utf-8')

xconv_options = {
    'version': '1.0.1.0',
    'conv_list' : None,
    'real_run': True,
    'args' : {},
    'ext_args_l1': [],
    'ext_args_l2': [],
    'work_dir': '.',
    'xresloader_path': 'xresloader.jar',

    'item': [],
    'parallelism': int((cpu_count() - 1) / 2) + 1
}
xconv_xml_global_nodes = []
xconv_xml_list_item_nodes = []


usage = "usage: %prog [options...] <convert list file> [xresloader options...]"
parser = OptionParser(usage)
parser.disable_interspersed_args()


parser.add_option("-v", "--version", action="store_true", help="show version and exit", dest="version", default=False)
parser.add_option("-s", "--scheme-name", action="append", help="only convert schemes with name <scheme name>", metavar="<scheme>",dest="rule_schemes", default=[])
parser.add_option("-t", "--test", action="store_true", help="test run and show cmds", dest="test", default=False)
parser.add_option("-p", "--parallelism", action="store", help="set parallelism task number(default:" + str(xconv_options['parallelism']) + ')', metavar="<number>", dest="parallelism", type="int", default=xconv_options['parallelism'])

(options, left_args) = parser.parse_args()

if options.version:
    print(xconv_options['version'])
    exit(0)

def print_help_msg(err_code):
    parser.print_help()
    exit(err_code)


if 0 == len(left_args):
    print_help_msg(-1)

xconv_options['conv_list'] = left_args.pop(0)
xconv_options['ext_args_l2'] = left_args

# ========================================= 全局配置解析 =========================================
''' 读取xml文件 '''
def load_xml_file(file_path):
    try:
        xml_doc = ET.parse(file_path)
    except Exception as e:
        print(e)
        exit(-2)

    root_node = xml_doc.getroot()

    if root_node == None:
        print('[ERROR] root node not found in xml')
        print_help_msg(-3)

    # 枚举include文件
    include_nodes = root_node.findall("./include")
    if include_nodes and len(include_nodes) > 0:
        dir_prefix = os.path.dirname(file_path)
        for include_node in include_nodes:
            include_file_path = include_node.text
            if include_file_path and len(include_file_path) > 1:
                if include_file_path[0] != '/' and include_file_path[1] != ':':
                    include_file_path = os.path.join(dir_prefix, include_file_path)
                load_xml_file(include_file_path)

    global_nodes = root_node.findall("./global")
    if global_nodes and len(global_nodes) > 0:
        xconv_xml_global_nodes.extend(global_nodes)

    list_item_nodes = root_node.findall("./list/item")
    if list_item_nodes and len(list_item_nodes) > 0:
        xconv_xml_list_item_nodes.extend(list_item_nodes)

load_xml_file(xconv_options['conv_list'])


''' global配置解析/合并 '''
def load_global_options(gns):
    for global_node in gns:
        for global_option in global_node:
            tag_name = global_option.tag.lower()
            text_value = global_option.text
            if text_value:
                trip_value = text_value.strip()
            else:
                trip_value = None

            if not trip_value:
                continue

            if 'work_dir' == tag_name:
                xconv_options['work_dir'] = text_value

            elif 'xresloader_path' == tag_name:
                xconv_options['xresloader_path'] = text_value

            elif 'proto' == tag_name:
                xconv_options['args']['-p'] = trip_value

            elif 'output_type' == tag_name:
                xconv_options['args']['-t'] = trip_value

            elif 'proto_file' == tag_name:
                xconv_options['args']['-f'] = '"' + text_value + '"'

            elif 'output_dir' == tag_name:
                xconv_options['args']['-o'] = '"' + text_value + '"'

            elif 'data_src_dir' == tag_name:
                xconv_options['args']['-d'] = '"' + text_value + '"'

            elif 'rename' == tag_name:
                xconv_options['args']['-n'] = '"' + trip_value + '"'

            elif 'option' == tag_name:
                xconv_options['ext_args_l1'].append(trip_value)

            else:
                print('[ERROR] unknown global configure ' + tag_name)

if xconv_xml_global_nodes and len(xconv_xml_global_nodes) > 0:
    load_global_options(xconv_xml_global_nodes)

# ----------------------------------------- 全局配置解析 -----------------------------------------

conv_list_dir = os.path.dirname(xconv_options['conv_list'])
os.chdir(conv_list_dir)
os.chdir(xconv_options['work_dir'])

cprintf_stdout([print_style.FC_YELLOW], '[NOTICE] start to run conv cmds on dir: {0}\n', os.getcwd())

if not os.path.exists(xconv_options['xresloader_path']):
    cprintf_stderr([print_style.FC_RED], '[ERROR] xresloader not found.({0})\n', xconv_options['xresloader_path'])
    exit(-4)

# ========================================= 转换表配置解析 =========================================

''' 转换项配置解析/合并 '''
def load_list_item_nodes(lis):
    for item in lis:
        conv_item_obj = {
            'file': item.attrib['file'],
            'scheme': item.attrib['scheme'],
            'options': [],
            'enable': False
        }

        # 局部选项
        for local_option in item.findall('./option'):
            tag_name = local_option.tag.lower()
            text_value = local_option.text
            if text_value:
                trip_value = text_value.strip()
            else:
                trip_value = None

            if not trip_value:
                continue

            if 'option' == tag_name:
                conv_item_obj['options'].append(trip_value)

        # 转换规则
        if not options.rule_schemes or 0 == len(options.rule_schemes) or conv_item_obj['scheme'] in options.rule_schemes:
            conv_item_obj['enable'] = True

        xconv_options['item'].append(conv_item_obj)

if xconv_xml_list_item_nodes and len(xconv_xml_list_item_nodes) > 0:
    load_list_item_nodes(xconv_xml_list_item_nodes)
# ----------------------------------------- 转换配置解析 -----------------------------------------


# ========================================= 生成转换命令 =========================================
##### 全局命令和配置
global_cmd_prefix = 'java -client -jar "{0}"'.format(xconv_options['xresloader_path'])
for global_optk in xconv_options['args']:
    global_optv= xconv_options['args'][global_optk]
    global_cmd_prefix += ' ' + global_optk + ' ' + global_optv

if len(xconv_options['ext_args_l1']) > 0:
    global_cmd_prefix += ' ' + ' '.join(xconv_options['ext_args_l1'])

##### 命令行参数
global_cmd_suffix = ''
if len(xconv_options['ext_args_l2']) > 0:
    global_cmd_suffix += ' ' + ' '.join(xconv_options['ext_args_l2'])

cmd_list=[]
for conv_item in xconv_options['item']:
    if not conv_item['enable']:
        continue

    item_cmd_options = ''
    if len(conv_item['options']) > 0:
        item_cmd_options += ' ' + ' '.join(conv_item['options'])

    cmd_scheme_info = ' -s "{:s}" -m "{:s}"'.format(conv_item['file'], conv_item['scheme'])
    run_cmd = global_cmd_prefix + item_cmd_options + cmd_scheme_info + global_cmd_suffix
    if 'utf-8' != console_encoding.lower():
        run_cmd = run_cmd.encode(console_encoding)

    cmd_list.append(run_cmd)

cmd_list.reverse()
# ----------------------------------------- 生成转换命令 -----------------------------------------

# ========================================= 实际开始转换 =========================================
import threading
exit_code = 0
all_worker_thread = []
cmd_picker_lock = threading.Lock()

def worker_func():
    global exit_code
    while True:
        cmd_picker_lock.acquire()
        if len(cmd_list) <= 0:
            cmd_picker_lock.release()
            return 0

        run_cmd = cmd_list.pop()
        cmd_picker_lock.release()

        cprintf_stdout([print_style.FC_GREEN], '[INFO] {0}\n', run_cmd)
        cmd_exit_code = 0
        if not options.test:
            cmd_exit_code = os.system(run_cmd)
        if cmd_exit_code < 0:
            exit_code = cmd_exit_code

for i in xrange(0, options.parallelism):
    this_worker_thd = threading.Thread(target=worker_func)
    this_worker_thd.start()
    all_worker_thread.append(this_worker_thd)


# 等待退出
for thd in all_worker_thread:
    thd.join()

# ----------------------------------------- 实际开始转换 -----------------------------------------

cprintf_stdout([print_style.FC_MAGENTA], '[INFO] all jobs done.\n')

exit(exit_code)