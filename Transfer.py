#!/usr/bin/env python
# coding: utf-8

'''
Support Python 2 and 3
Transfer helps you transfer data from Pythonista to Pythonista and PC to
Pythonista and PC to PC.

Your devices must be in the same network

Adding shortcuts makes it easy to use.
See image files in https://github.com/nekotaroneko/Transfer
'''

import datetime
import glob
import json
import os
import platform
import re
import requests
import shutil
import socket
import sys
import threading
import time
import zipfile
from six.moves import input, BaseHTTPServer, SimpleHTTPServer


def is_pythonista():
	return 'Pythonista' in sys.executable

pythonista = is_pythonista()

if pythonista:
	import console
	import clipboard
	import appex
	if not appex.is_running_extension():
		import editor


def stash_installer():
	'''this function is not used in this script'''
	try:
		from stash.stash import StaSh
	except:
		import requests
		exec(requests.get('http://bit.ly/get-stash').text, globals(), locals())
	finally:
		from stash.stash import StaSh


def to_abs_path(*value):
	abs_path = os.path.expanduser('~')
	if pythonista:
		abs_path = os.path.join(abs_path, 'Documents')
	for _value in value:
		abs_path = os.path.join(abs_path, _value)
	return abs_path


# File Picker
# quoted from https://gist.github.com/omz/e3433ebba20c92b63111
# for those who cannot use wrench menu
def file_picker():
	import ui
	from objc_util import ObjCInstance, ObjCClass
	from operator import attrgetter
	import functools

	class TreeNode (object):
		def __init__(self):
			self.expanded = False
			self.children = None
			self.leaf = True
			self.title = ''
			self.subtitle = ''
			self.icon_name = None
			self.level = 0
			self.enabled = True

		def expand_children(self):
			self.expanded = True
			self.children = []

		def collapse_children(self):
			self.expanded = False

		def __repr__(self):
			return '<TreeNode: "%s"%s>' % (self.title,
											' (expanded)' if self.expanded else '')

	class FileTreeNode (TreeNode):
		def __init__(self, path, show_size=True, select_dirs=True,
						file_pattern=None):
			TreeNode.__init__(self)
			self.path = path
			self.title = os.path.split(path)[1]
			self.select_dirs = select_dirs
			self.file_pattern = file_pattern
			is_dir = os.path.isdir(path)
			self.leaf = not is_dir
			ext = os.path.splitext(path)[1].lower()
			if is_dir:
				self.icon_name = 'Folder'
			elif ext == '.py':
				self.icon_name = 'FilePY'
			elif ext == '.pyui':
				self.icon_name = 'FileUI'
			elif ext in ('.png', '.jpg', '.jpeg', '.gif'):
				self.icon_name = 'FileImage'
			else:
				self.icon_name = 'FileOther'
			self.show_size = show_size
			if not is_dir and show_size:
				self.subtitle = human_size((os.stat(self.path).st_size))
			if is_dir and not select_dirs:
				self.enabled = False
			elif not is_dir:
				filename = os.path.split(path)[1]
				self.enabled = not file_pattern or re.match(file_pattern, filename)

		@property
		def cmp_title(self):
			return self.title.lower()

		def expand_children(self):
			if self.children is not None:
				self.expanded = True
				return
			files = os.listdir(self.path)
			children = []
			for i, filename in enumerate(files):
				if filename.startswith('.'):
					continue

				full_path = os.path.join(self.path, filename)
				node = FileTreeNode(full_path, self.show_size, self.select_dirs,
									self.file_pattern)
				node.level = self.level + 1
				children.append(node)

			self.expanded = True
			self.children = sorted(children, key=attrgetter('leaf', 'cmp_title'))

	class TreeDialogController (object):
		def __init__(self, root_node, allow_multi=False, async_mode=False):
			self.async_mode = async_mode
			self.allow_multi = allow_multi
			self.selected_entries = None
			self.table_view = ui.TableView()
			self.table_view.frame = (0, 0, 500, 500)
			self.table_view.data_source = self
			self.table_view.delegate = self
			self.table_view.flex = 'WH'
			self.table_view.allows_multiple_selection = True
			self.table_view.tint_color = 'gray'
			self.view = ui.View(frame=self.table_view.frame)
			self.view.add_subview(self.table_view)
			self.view.name = root_node.title
			self.busy_view = ui.View(frame=self.view.bounds, flex='WH',
										background_color=(0, 0, 0, 0.35))
			hud = ui.View(frame=(self.view.center.x - 50, self.view.center.y - 50,
									100, 100))
			hud.background_color = (0, 0, 0, 0.7)
			hud.corner_radius = 8.0
			hud.flex = 'TLRB'
			spinner = ui.ActivityIndicator()
			spinner.style = ui.ACTIVITY_INDICATOR_STYLE_WHITE_LARGE
			spinner.center = (50, 50)
			spinner.start_animating()
			hud.add_subview(spinner)
			self.busy_view.add_subview(hud)
			self.busy_view.alpha = 0.0
			self.view.add_subview(self.busy_view)
			self.done_btn = ui.ButtonItem(title='Done', action=self.done_action)
			self.root_btn = ui.ButtonItem(title='Root', action=self.root_btn_action)
			self.mobile_btn = ui.ButtonItem(title='Mobile',
											action=self.mobile_btn_action)
			if self.allow_multi:
				self.view.right_button_items = [self.done_btn, self.mobile_btn,
												self.root_btn]
			self.done_btn.enabled = False
			self.root_node = root_node
			self.entries = []
			self.flat_entries = []
			if self.async_mode:
				self.set_busy(True)
				t = threading.Thread(target=self.expand_root)
				t.start()
			else:
				self.expand_root()

		def expand_root(self):
			self.root_node.expand_children()
			self.set_busy(False)
			self.entries = self.root_node.children
			self.flat_entries = self.entries
			self.table_view.reload()

		def flatten_entries(self, entries, dest=None):
			dest = dest or []
			for entry in entries:
				dest.append(entry)
				if not entry.leaf and entry.expanded:
					self.flatten_entries(entry.children, dest)
			return dest

		def rebuild_flat_entries(self):
			self.flat_entries = self.flatten_entries(self.entries)

		def tableview_number_of_rows(self, tv, section):
			return len(self.flat_entries)

		def tableview_cell_for_row(self, tv, section, row):
			cell = ui.TableViewCell()
			entry = self.flat_entries[row]
			level = entry.level - 1
			image_view = ui.ImageView(frame=(44 + 20 * level, 5, 34, 34))
			label_x = 44 + 34 + 8 + 20 * level
			label_w = cell.content_view.bounds.w - label_x - 8
			if entry.subtitle:
				label_frame = (label_x, 0, label_w, 26)
				sub_label = ui.Label(frame=(label_x, 26, label_w, 14))
				sub_label.font = ('<System>', 12)
				sub_label.text = entry.subtitle
				sub_label.text_color = '#999'
				cell.content_view.add_subview(sub_label)
			else:
				label_frame = (label_x, 0, label_w, 44)
			label = ui.Label(frame=label_frame)
			label.font = ('<System>', 15 if entry.subtitle else 18)
			label.text = entry.title
			label.flex = 'W'
			cell.content_view.add_subview(label)
			if entry.leaf and not entry.enabled:
				label.text_color = '#999'
			cell.content_view.add_subview(image_view)
			if not entry.leaf:
				has_children = entry.expanded
				image_name = 'CollapseFolder' if has_children else 'ExpandFolder'
				btn = ui.Button(image=ui.Image.named(image_name))
				btn.frame = (20 * level, 0, 44, 44)
				btn.action = self.expand_dir_action
				cell.content_view.add_subview(btn)
			if entry.icon_name:
				image_view.image = ui.Image.named(entry.icon_name)
			else:
				image_view.image = None
			cell.selectable = entry.enabled
			return cell

		def row_for_view(self, sender):
			'''Helper to find the row index for an 'expand' button'''
			cell = ObjCInstance(sender)
			while not cell.isKindOfClass_(ObjCClass('UITableViewCell')):
				cell = cell.superview()
			return ObjCInstance(self.table_view).indexPathForCell_(cell).row()

		def expand_dir_action(self, sender):
			'''Invoked by 'expand' button'''
			row = self.row_for_view(sender)
			entry = self.flat_entries[row]
			image_name = 'ExpandFolder' if entry.expanded else 'CollapseFolder'
			sender.image = ui.Image.named(image_name)
			self.toggle_dir(row)
			self.update_done_btn()

		def toggle_dir(self, row):
			'''Expand or collapse a folder node'''
			entry = self.flat_entries[row]
			if entry.expanded:
				entry.collapse_children()
				old_len = len(self.flat_entries)
				self.rebuild_flat_entries()
				num_deleted = old_len - len(self.flat_entries)
				deleted_rows = range(row + 1, row + num_deleted + 1)
				self.table_view.delete_rows(deleted_rows)
			else:
				if self.async_mode:
					self.set_busy(True)
					expand = functools.partial(self.do_expand, entry, row)
					t = threading.Thread(target=expand)
					t.start()
				else:
					self.do_expand(entry, row)

		def do_expand(self, entry, row):
			'''Actual folder expansion (called on background thread if async_mode is
				enabled)'''
			entry.expand_children()
			self.set_busy(False)
			old_len = len(self.flat_entries)
			self.rebuild_flat_entries()
			num_inserted = len(self.flat_entries) - old_len
			inserted_rows = range(row + 1, row + num_inserted + 1)
			self.table_view.insert_rows(inserted_rows)

		def tableview_did_select(self, tv, section, row):
			self.update_done_btn()

		def tableview_did_deselect(self, tv, section, row):
			self.update_done_btn()

		def update_done_btn(self):
			'''Deactivate the done button when nothing is selected'''
			selected = [self.flat_entries[i[1]] for i in self.table_view.selected_rows
						if self.flat_entries[i[1]].enabled]
			if selected and not self.allow_multi:
				self.done_action(None)
			else:
				self.done_btn.enabled = len(selected) > 0

		def set_busy(self, flag):
			'''Show/hide spinner overlay'''
			def anim():
				self.busy_view.alpha = 1.0 if flag else 0.0
			ui.animate(anim)

		def done_action(self, sender):
			self.selected_entries = [self.flat_entries[i[1]] for i
										in self.table_view.selected_rows
										if self.flat_entries[i[1]].enabled]
			self.view.close()

		def root_btn_action(self, sender):
			root_node = FileTreeNode('/', True, True, r'^.+$')
			self.root_node = root_node
			self.expand_root()

		def mobile_btn_action(self, sender):
			root_node = FileTreeNode('/var/mobile', True, True, r'^.+$')
			self.root_node = root_node
			self.expand_root()

	def file_picker_dialog(title=None, root_dir=None, multiple=False,
							select_dirs=False, file_pattern=None, show_size=True):
		root_dir = root_dir or os.path.expanduser('~/Documents')
		title = title or os.path.split(root_dir)[1]
		root_node = FileTreeNode(root_dir, show_size, select_dirs, file_pattern)
		root_node.title = title or ''
		picker = TreeDialogController(root_node, allow_multi=multiple)
		picker.view.present('sheet')
		picker.view.wait_modal()
		if picker.selected_entries is None:
			return None
		paths = [e.path for e in picker.selected_entries]
		return paths if multiple else paths[0]
	return file_picker_dialog
	# File Picker


# http://stackoverflow.com/a/6547474
def human_size(size_bytes, no_suffixs=False):
	'''Helper function for formatting human-readable file sizes'''
	if size_bytes == 1:
		return "1 byte"
	suffixes_table = [('bytes', 0), ('KB', 0), ('MB', 1), ('GB', 2), ('TB', 2),
						('PB', 2)]
	num = float(size_bytes)
	for suffix, precision in suffixes_table:
		if num < 1024.0:
			break
		num /= 1024.0
	formatted_size = str(round(num, ndigits=precision)) if precision else "%d" % num
	return formatted_size if no_suffixs else "%s %s" % (formatted_size, suffix)


# ----------------------Main Code--------------------

class Transfer(object):
	def __init__(self, main_dir, port):
		self.comment_dict = {}
		self.port = port
		self.main_dir = main_dir
		self.send_path = to_abs_path(main_dir, "SendFile.zip")
		self.receive_path = to_abs_path(main_dir, "ReceiveFile.zip")
		self.comment_dict['send_path'] = self.send_path  # to multiply file size
		self.comment_dict['receive_path'] = self.receive_path # to multiply file size
		if os.path.isfile(self.send_path):
			os.remove(self.send_path)
		system = platform.system()
		self.system = 'Pythonista' if pythonista else system

	def send(self, file_list):
		if pythonista:
			console.set_idle_timer_disabled(True)
		print('Archiving files.....')

		self.comment_dict['sender'] = self.system
		comment_str = json.dumps(self.comment_dict)
		archiver(file_list, True, self.send_path, comment_str)

		self.start_server()
		if self.system == 'Windows':
			os.system('pause')

	def receive(self, wait_time, show_text=True):
		if pythonista:
			console.set_idle_timer_disabled(True)
		main_dir = self.main_dir

		if os.path.isfile(self.receive_path):
			os.remove(self.receive_path)
		try:
			while True:
				if show_text:
					print('Detecting Server.....')
				result = port_scan.scan()
				if result:
					IP = result[0]
					break
				if show_text:
					print('waiting for {}s'.format(wait_time))
				time.sleep(wait_time)
		except KeyboardInterrupt:
			raise KeyboardInterrupt

		d = datetime.datetime.today().strftime("%Y-%m-%d %H-%M-%S")
		to_extract_path = to_abs_path(main_dir, d)

		print('Detected!!\nServer IP is ' + IP)
		rel_path = os.path.relpath(self.send_path, to_abs_path())
		rel_path = rel_path.replace("\\", "/")  # for windows
		target_url = 'http://{}:{}/{}'.format(IP, port, rel_path)
		downloader(target_url, self.receive_path)
		if os.path.exists(self.receive_path):
			if pythonista:
				console.hud_alert('Transfer Completed!!')
			if not os.path.isdir(to_extract_path):
				os.makedirs(to_extract_path)
			zip = zipfile.ZipFile(self.receive_path)
			receive_comment_dict = json.loads(zip.comment.decode('utf-8'))
			print('\nExtracting.....')
			sender = receive_comment_dict['sender']
			for _ in zip.infolist():
				decoding = 'shift-jis' if sender == 'Windows' else 'utf-8'
				_.filename = _.filename.encode('utf-8').decode(decoding, 'replace')
				try:
					zip.extract(_, to_extract_path)
				except:
					new_filename = []
					sep = '//' if sender == 'Windows' else '/'
					for split in _.filename.split(sep):
						_split = re.sub(r'[\\|/|:|?|"|<|>|\|]', '-', split).strip()
						new_filename.append(_split)
					new_filename = sep.join(new_filename)
					_.filename = new_filename

					try:
						zip.extract(_, to_extract_path)
					except Exception as e:
						print('Error {}'.format(_.filename))
						print(e)
					else:
						print('Renamed {}'.format(_.filename))

			zip.close()
			os.remove(self.receive_path)
			if 'share_text' in receive_comment_dict:
				share_text = receive_comment_dict['share_text']
				if pythonista:
					clipboard.set(share_text)
					console.hud_alert('Copied to clipboard')
				elif self.system == 'Windows':
					os.system('echo {}|clip'.format(share_text))
					print('Copied to clipboard')
					print('Share text \n"\n{}\n"'.format(share_text))
				else:
					print('Share text \n"\n{}\n"'.format(share_text))
				removeEmptyFolders(to_extract_path, True)

			elif pythonista and receive_comment_dict['sender'] == 'Pythonista':
				msg = "Sender is Pythonista\nMove to original path?"
				if console.alert("Transfer", msg, "No", "Yes",
									hide_cancel_button=True) == 2:
					print('-----Detailed Log-----\n')
					file_list = [(to_abs_path(os.path.relpath(x, to_extract_path)), x)
									for x in return_all_file(to_extract_path)]
					total_file_list = []  # file not dir

					# print(file_list
					replace_list = []
					for original_path, transfer_path in file_list:
						if os.path.isfile(original_path):
							replace_list.append([original_path, transfer_path])

						if os.path.isdir(transfer_path):
							if not os.path.isdir(original_path):
								os.makedirs(original_path)
								fmt = 'dir {} was creadted'
								print(fmt.format(os.path.relpath(original_path, to_abs_path())))
						else:
							if not os.path.isfile(original_path):
								shutil.move(transfer_path, original_path)
								fmt = 'moved {} to {}'
								print(fmt.format(os.path.relpath(transfer_path, to_abs_path()),
													os.path.relpath(original_path, to_abs_path())))
								total_file_list.append(original_path)

					if replace_list and console.alert("Transfer", "Following files will be replaced.\n{}".format('\n'.join([os.path.relpath(x, to_abs_path()) for x, y in replace_list])), "No", "OK", hide_cancel_button=True) == 2:
						for original_path, transfer_path in replace_list:
							os.remove(original_path)
							print('{} was removed'.format(os.path.relpath(original_path,
																			to_abs_path())))
							shutil.move(transfer_path, original_path)
							fmt = 'moved {} to {}'
							print(fmt.format(os.path.relpath(transfer_path, to_abs_path()),
												os.path.relpath(original_path, to_abs_path())))
							total_file_list.append(original_path)

					removeEmptyFolders(to_extract_path, True)
					if len(total_file_list) == 1:
						ab_file_path = total_file_list[0]
						re_file_path = os.path.relpath(ab_file_path, to_abs_path())
						msg = 'Do you want to open {}?'.format(re_file_path)
						if console.alert("Transfer", msg, "No", "Yes",
											hide_cancel_button=True) == 2:
							editor.open_file(ab_file_path, True)
			else:
				msg = 'Sender is {sender}'.format(**receive_comment_dict)
				if pythonista:
					console.hud_alert(msg)
				else:
					print(msg)
			if 'share_text' not in receive_comment_dict:
				if self.system == 'Windows':
					os.system('explorer.exe {}'.format(to_extract_path))
				elif self.system == 'Linux':
					os.system('nautilus "{}"'.format(to_extract_path))
			print('Done!!')
			if self.system == 'Windows':
				os.system('pause')
		else:
			console.alert("Transfer", "{} is not found".format(self.receive_path), "OK",
																hide_cancel_button=True)

	def start_server(self):
		def do_GET(self):
			"""Serve a GET request."""
			f = self.send_head()
			if f:
				try:
					self.copyfile(f, self.wfile)
				finally:
					f.close()
					t = threading.Thread(target=self.server.shutdown)
					t.daemon = True
					t.start()
					print('File transfer was completed.Server is shutdowning.....')

		def translate_path(self, path):
			"""Translate a /-separated PATH to the local filename syntax.

			Components that mean special things to the local file system
			(e.g. drive or directory names) are ignored.  (XXX They should
			probably be diagnosed.)
			"""
			import posixpath
			from six.moves.urllib_parse import unquote
			# abandon query parameters
			path = path.split('?', 1)[0]
			path = path.split('#', 1)[0]
			# Don't forget explicit trailing slash when normalizing. Issue17324
			trailing_slash = path.rstrip().endswith('/')
			path = posixpath.normpath(unquote(path))
			words = filter(None, path.split('/'))
			path = to_abs_path()
			for word in words:
				if os.path.dirname(word) or word in (os.curdir, os.pardir):
					# Ignore components that are not a simple file/directory name
					continue
				path = os.path.join(path, word)
			if trailing_slash:
				path += '/'
			return path

		print('Starting Server.....')
		SimpleHTTPServer.SimpleHTTPRequestHandler.do_GET = do_GET
		SimpleHTTPServer.SimpleHTTPRequestHandler.translate_path = translate_path
		try:
			server = BaseHTTPServer.HTTPServer(('', self.port),
												SimpleHTTPServer.SimpleHTTPRequestHandler)
		except Exception as e:
			print(e)
			print('Server has already started')
		else:
			thread = threading.Thread(target=server.serve_forever, name='server')
			thread.deamon = True
			thread.start()
			thread.join()
			os.remove(self.send_path)

	def send_text(self, share_text):
		print('Sending the text\n"{}"'.format(share_text))
		self.comment_dict['share_text'] = share_text
		self.send([])


def search_all_file(file_dir_list):
	file_list = []
	for _ in file_dir_list:
		if os.path.isdir(_):
			file_list.extend(return_all_file(_))
		else:
			file_list.append(_)
	return file_list


def return_all_file(dir_path):
	file_list = []
	if os.path.isdir(dir_path):
		while True:
			dir_path += "/*"
			_list = glob.glob(dir_path)
			# print(len(_list))
			if len(_list) == 0:
				break
			else:
				file_list.extend(_list)

	return file_list


def removeEmptyFolders(path, removeRoot=True):
	'Function to remove empty folders'
	if not os.path.isdir(path):
		return

	# remove empty subfolders
	files = os.listdir(path)
	for f in files:
		fullpath = os.path.join(path, f)
		if os.path.isdir(fullpath):
			removeEmptyFolders(fullpath)

	# if folder empty, delete it
	if removeRoot:
		if len(os.listdir(path)) == 0:
			# print("Removing empty folder:", path)
			os.rmdir(path)


class Port_Scan(object):
	def __init__(self, port, alert=True):
		self.port = port
		self.alert = alert
		self.current_ip = self.get_ip()
		assert self.current_ip, 'Cannot find IP'
		print('This device IP is {}'.format(self.current_ip))
		self.thread_limit = threading.Semaphore(100)

	def pscan(self, ip, port):
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
			s.settimeout(1)
			s.connect((ip, port))
			s.close()
		except:
			# print('Port',port,'is close')
			return False
		else:
			if ip == self.current_ip:
				return False
			else:
				self.result.append(ip)
		finally:
			self.thread_limit.release()

	def scan(self):
		self.result = []
		_gate_way = '.'.join(self.current_ip.split('.')[:3])
		# gate_way = _gate_way+'.1'  # pyflakes says this is not used
		if self.alert:
			console.show_activity('Scanning.....')
		for x in range(1, 256):
			ip = '{}.{}'.format(_gate_way, x)
			self.thread_limit.acquire()
			threading.Thread(target=self.pscan, args=(ip, self.port),
								name='PortScanner').start()

		thread_list = [x for x in threading.enumerate() if x.name == 'PortScanner']
		for _ in thread_list:
			_.join()
		if self.alert:
			if self.result:
				console.hud_alert(' '.join(self.result), 'success', 1)
			else:
				console.hud_alert('Not found', 'error', 1)
			console.hide_activity()
		return self.result

	def get_ip(self):
		try:
			s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
			s.connect(("8.8.8.8", 80))
			ip = s.getsockname()[0]
			s.close()
			return ip
		except:
			# offline
			if pythonista:
				try:
					from objc_util import ObjCClass
					NSHost = ObjCClass('NSHost')
					addresses = []
					for address in NSHost.currentHost().addresses():
						address = str(address)
						if 48 <= ord(address[0]) <= 57 and address != '127.0.0.1':
							addresses.append(address)
					# return '   '.join(addresses)
					return addresses[-1]
				except ImportError:
					return ''
			else:
				# PC
				import subprocess
				try:
					result = subprocess.check_output('ifconfig en0 | grep -w inet',
														shell=True)
				except:
					try:
						result = subprocess.check_output('ifconfig eth0 | grep -w inet',
															shell=True)
					except:
						return False
				ip = ''
				if result:
					strs = result.split('\n')
					for line in strs:
						# remove \t, space...
						line = line.strip()
						if line.startswith('inet '):
							a = line.find(' ')
							ipStart = a + 1
							ipEnd = line.find(' ', ipStart)
							if a != -1 and ipEnd != -1:
								ip = line[ipStart:ipEnd]
								break

					return ip


def downloader(url, file_path, progress=True, style=1):
	_file_path = os.path.basename(file_path)
	with open(file_path, "wb") as f:
		print("Downloading %s" % _file_path)
		response = requests.get(url, stream=True)
		total_length = response.headers.get('content-length')

		if total_length is None:  # no content length header
			f.write(response.content)
		else:
			dl = 0
			total_length = int(total_length)
			dl_time = time.time()
			dl_speed = 0
			dl_size_per_sec = 0
			one_sec_passed = False
			eta = 0
			for data in response.iter_content(chunk_size=int(total_length / 100)):
				dl += len(data)
				f.write(data)
				done = int(50 * dl / total_length)
				percent = int(100 * dl / total_length)
				dl_size_per_sec += len(data)
				if time.time() - dl_time >= 1:
					# to get dl speed
					dl_time = time.time()
					dl_speed = human_size(dl_size_per_sec)
					eta = (total_length - dl) / dl_size_per_sec
					dl_size_per_sec = 0
					one_sec_passed = True

				eta_min = int(eta / 60)
				eta_sec = int(eta % 60)
				if eta_min == 0 and eta_sec == 0:
					eta_text = "∞"
				else:
					eta_text = "{:02}:{:02}".format(eta_min, eta_sec)
				if percent == 100:
					eta_text = "00:00"
				if progress:
					if style == 1:
						fmt = "\r[{}{}]{} {}% {}/s {} "
						sys.stdout.write(fmt.format('=' * done, ' ' * (50 - done),
													human_size(total_length), percent,
													dl_speed if one_sec_passed else human_size(dl_size_per_sec),
													eta_text))
					if style == 2:
						fmt = "\r{}/{} {}％ {}/s {} "
						sys.stdout.write(fmt.format(human_size(dl, True),
													human_size(total_length), percent,
													dl_speed if one_sec_passed else human_size(dl_size_per_sec),
													eta_text))
					sys.stdout.flush()


def archiver(files, hide=False, to_path=False, comment=None):
	if not to_path:
		to_path = os.path.basename(files[0]) + '.zip'
	file_list = search_all_file(files)
	path_pat = re.compile('.+?Documents')
	path_arcname_list = [[x, path_pat.sub("", x)] for x in file_list]
	with zipfile.ZipFile(to_path, "w", zipfile.ZIP_DEFLATED,
							allowZip64=True) as zf:
		if comment:
			zf.comment = comment.encode('utf-8')
		for path, arcname in path_arcname_list:
			if not pythonista and len(file_list) == 1:
				arcname = os.path.basename(path)
			if not hide:
				print("adding " + arcname)
			zf.write(path, arcname)

		'''for _ in zf.infolist():
			_.comment = _.filename.encode('utf-8')#encode('shift-jis', 'replace')'''


def select():
	result = console.alert("", "Select", "Send", "Receive", 'Cancel',
							hide_cancel_button=True)
	if result == 1:
		files = file_picker()('Pick files', multiple=True, select_dirs=True,
								file_pattern=r'^.+$')
		if files:
			transfer.send(files)
	elif result == 2:
		transfer.receive(wait_interval)


def get_selected_text():
	if appex.is_running_extension():
		return False
	text = editor.get_text()
	s = editor.get_selection()
	return text[s[0]:s[1]] or False


def start_up():
	'''always receive mode'''
	def _start_up():
		while True:
			transfer.receive(wait_interval, False)
	console.hide_output()
	print('Ready to receive.....')
	threading.Thread(target=_start_up, name='Transfer_Startup').start()


main_dir = "Transfer"
port = 8765
wait_interval = 1  # sec multiply this value if something error happened

main_dir = to_abs_path(main_dir)
if not os.path.isdir(main_dir):
	os.makedirs(main_dir)

transfer = Transfer(main_dir, port)
port_scan = Port_Scan(port, False)

if __name__ == '__main__':
	args = sys.argv
	user_args = args[1:]
	if pythonista:
		# Pythonista
		if sys.version[0] == '3' and appex.is_widget():
			start_up()
		elif 'select' in user_args:
			select()
		elif 'send' in user_args:
			files = file_picker('Pick files', multiple=True, select_dirs=True,
								file_pattern=r'^.+$')
			if files:
				transfer.send(files)
		elif 'receive' in user_args:
			transfer.receive(wait_interval)
		elif 'send_selected_or_clipboard_text' in user_args:
			share_text = get_selected_text()
			if not share_text:
				share_text = clipboard.get()
			transfer.send_text(share_text)
		elif user_args:
			files = user_args
			print(files)
			transfer.send(files)
		else:
			if appex.is_running_extension():
				path = appex.get_file_paths()
				if len(path) == 0:
					path = appex.get_attachments()
				# print(appex.get_file_path()
				print(path)
				if not len(path) == 0:
					if len(path) == 1 and not os.path.isfile(path[0]):
						share_text = path[0]
						msg = "Do you want to share this text?\n{}".format(share_text)
						if console.alert("Transfer", msg, "No", "Yes",
											hide_cancel_button=True) == 2:
							transfer.send_text(share_text)
					else:
						transfer.send(path)
			else:
				share_text = get_selected_text()
				if share_text:
					fmt = "Do you want to share this text?\n{}"
					if console.alert("Transfer", fmt.format(share_text), "No", "Yes",
										hide_cancel_button=True) == 2:
						transfer.send_text(share_text)
				else:
					select()
	else:
		# PC
		if user_args:
			files = user_args
			print(files)
			transfer.send(files)
		else:
			print('Working Dir {}'.format(main_dir))
			print('1 : Send file\n2 : Receive file/text\n3 : Share text')
			result = input().strip()
			if result == '1':
				print('You can also use Transfer.py file1 file2 file3...')
				print('Path>>')
				path = input().strip().strip("'").strip('"')
				transfer.send([path])
			elif result == '2':
				transfer.receive(wait_interval, True)
			elif result == '3':
				print('Text>>')
				transfer.send_text(input().strip())
