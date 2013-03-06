#!/usr/bin/env python
# -*- coding:utf-8 -*-
#
#   Author  :   cold
#   E-mail  :   wh_linux@126.com
#   Date    :   13/02/28 11:23:49
#   Desc    :   Web QQ API
#
import time
import json
import random
import socket
import tempfile
import threading
from hashlib import md5
from functools import partial
from util import HttpHelper, get_logger, upload_file

from http_socket import HTTPSock

from pyxmpp2.mainloop.interfaces import (IOHandler, HandlerReady, Event,
                                         PrepareAgain)

http_sock = HTTPSock()

class WebQQEvent(Event):
    webqq = None
    handler = None

class CheckedEvent(WebQQEvent):
    def __init__(self, check_data, handler):
        self.check_data = check_data
        self.handler = handler

    def __unicode__(self):
        return u"WebQQ Checked: {0}".format(self.check_data)


class BeforeLoginEvent(WebQQEvent):
    def __init__(self, back_data, handler):
        self.back_data = back_data
        self.handler = handler

    def __unicode__(self):
        return u"WebQQ Before Login: {0}".format(self.back_data)


class WebQQLoginedEvent(WebQQEvent):
    def __init__(self, handler):
        self.handler = handler

    def __unicode__(self):
        return u"WebQQ Logined"


class WebQQHeartbeatEvent(WebQQEvent):
    def __init__(self, handler):
        self.handler = handler

    def __unicode__(self):
        return u"WebQQ Heartbeat"


class WebQQPollEvent(WebQQEvent):
    def __init__(self, handler):
        self.handler = handler

    def __unicode__(self):
        return u"WebQQ Poll"


class WebQQMessageEvent(WebQQEvent):
    def __init__(self, msg, handler):
        self.handler = handler
        self.message = msg

    def __unicode__(self):
        return u"WebQQ Got msg: {0}".format(self.message)


class WebQQHandler(IOHandler):
    def __init__(self, webqq, *args, **kwargs):
        self._readable = False
        self._writable = True
        self.webqq = webqq
        self.lock = threading.RLock()
        self._cond = threading.Condition(self.lock)
        self.setup(*args, **kwargs)

    def fileno(self):
        with self.lock:
            if self.sock is not None:
                return self.sock.fileno()

        return None

    def is_readable(self):
        return self.sock is not None and self._readable

    def wait_for_readability(self):
        with self.lock:
            while True:
                if self.sock is None or not self._readable:
                    return False
                else:
                    return True
            self._cond.wait()


    def is_writable(self):
        with self.lock:
            return self.sock and self.data and self._writable

    def wait_for_writability(self):
        with self.lock:
            while True:
                if self.sock and self.data and self._writable:
                    return True
                else:
                    return False
            self._cond.wait()

    def prepare(self):
        return HandlerReady()

    def handle_read(self):
        pass

    def handle_hup(self):
        with self.lock:
            pass

    def handle_write(self):
        pass

    def handle_err(self):
        with self.lock:
            self.sock.close()

    def handle_nval(self):
        if self.sock is None:
            return

    def close(self):
        self.sock.close()

class CheckHandler(WebQQHandler):
    """ 检查是否需要验证码
    url : http://check.ptlogin2.qq.com/check
    接口返回:
        ptui_checkVC('0','!PTH','\x00\x00\x00\x00\x64\x74\x8b\x05');
        第一个参数表示状态码, 0 不需要验证, 第二个为验证码, 第三个为uin
    """
    def setup(self):
        url = "http://check.ptlogin2.qq.com/check"
        params = {"uin":self.webqq.qid, "appid":self.webqq.aid,
                  "r" : random.random()}
        self.method = "GET"
        self.req = http_sock.make_request(url, params, self.method)
        self.sock, self.data = http_sock.make_http_sock_data(self.req)

    def handle_read(self):
        self._readable = False
        resp = http_sock.make_response(self.sock, self.req, self.method)
        self.webqq.check_data = resp.read()
        self.webqq.event(CheckedEvent(self.webqq.check_data, self))

    def handle_write(self):
        self.sock.sendall(self.data)
        self._writable = False
        self._readable = True

class BeforeLoginHandler(WebQQHandler):
    """ 登录之前的操作
    :接口返回
        ptuiCB('0','0','http://www.qq.com','0','登录成功!', 'qxbot');
    先检查是否需要验证码,不需要验证码则首先执行一次登录
    然后获取Cookie里的ptwebqq,skey保存在实例里,供后面的接口调用
    """
    def setup(self, password):
        password = self.webqq.handle_pwd(password)
        params = [("u",self.webqq.qid), ("p",password),
                  ("verifycode", self.webqq.check_code), ("webqq_type",10),
                  ("remember_uin", 1),("login2qq",1),
                  ("aid", self.webqq.aid), ("u1", "http://www.qq.com"),
                  ("h", 1), ("ptredirect", 0), ("ptlang", 2052), ("from_ui", 1),
                  ("pttype", 1), ("dumy", ""), ("fp", "loginerroralert"),
                  ("mibao_css","m_webqq"), ("t",1),
                  ("g",1), ("js_type",0), ("js_ver", 10021)]
        url = "https://ssl.ptlogin2.qq.com/login"
        self.method = "GET"
        self.req = http_sock.make_request(url, params, self.method)
        if self.webqq.require_check:
            self.req.add_header("Referer", "https://ui.ptlogin2.qq.com/cgi-"
                                "bin/login?target=self&style=5&mibao_css=m_"
                                "webqq&appid=1003903&enable_qlogin=0&no_ver"
                                "ifyimg=1&s_url=http%3A%2F%2Fweb.qq.com%2Fl"
                                "oginproxy.html&f_url=loginerroralert&stron"
                                "g_login=1&login_state=10&t=20130221001")

        self.sock, self.data = http_sock.make_http_sock_data(self.req)

    def handle_write(self):
        self.sock.sendall(self.data)
        self._readable = True
        self._writable = False

    def handle_read(self):
        self._readable = False
        resp = http_sock.make_response(self.sock, self.req, self.method)
        self.webqq.blogin_data = resp.read().decode("utf-8")
        self.webqq.event(BeforeLoginEvent(self.webqq.blogin_data, self))
        eval("self.webqq."+self.webqq.blogin_data.rstrip().rstrip(";"))


class LoginHandler(WebQQHandler):
    """ 利用前几步生成的数据进行登录
    :接口返回示例
        {u'retcode': 0,
        u'result': {
            'status': 'online', 'index': 1075,
            'psessionid': '', u'user_state': 0, u'f': 0,
            u'uin': 1685359365, u'cip': 3673277226,
            u'vfwebqq': u'', u'port': 43332}}
        保存result中的psessionid和vfwebqq供后面接口调用
    """
    def setup(self):
        url = "http://d.web2.qq.com/channel/login2"
        params = [("r", '{"status":"online","ptwebqq":"%s","passwd_sig":"",'
                   '"clientid":"%d","psessionid":null}'\
                   % (self.webqq.ptwebqq, self.webqq.clientid)),
                  ("clientid", self.webqq.clientid),
                  ("psessionid", "null")
                  ]
        self.method = "POST"
        self.req = http_sock.make_request(url, params, self.method)

        self.req.add_header("Referer", "http://d.web2.qq.com/proxy.html?"
                                "v=20110331002&callback=1&id=3")
        self.req.add_header("Origin", "http://d.web2.qq.com")
        self.sock, self.data = http_sock.make_http_sock_data(self.req)

    def handle_write(self):
        self._writable = False
        self.sock.sendall(self.data)
        #body = "\r\n\r\n".join(self.data.split("\r\n\r\n")[1:])
        #self.sock.sendall(body)
        self._readable = True

    def handle_read(self):
        self._readable = False
        resp = http_sock.make_response(self.sock, self.req, self.method)
        tmp = resp.read()
        data = json.loads(tmp)
        self.webqq.vfwebqq = data.get("result", {}).get("vfwebqq")
        self.webqq.psessionid = data.get("result", {}).get("psessionid")
        self.webqq.event(WebQQLoginedEvent(self))


class HeartbeatHandler(WebQQHandler):
    """ 心跳 """
    def setup(self, delay = 0):
        self._readable = False
        self.delay = delay
        url = "http://web.qq.com/web2/get_msg_tip"
        params = [("uin", ""), ("tp", 1), ("id", 0), ("retype", 1),
                    ("rc", self.webqq.rc), ("lv", 2),
                  ("t", int(self.webqq.hb_last_time * 1000))]
        self.method = "GET"
        self.req = http_sock.make_request(url, params, self.method)
        self.sock, self.data = http_sock.make_http_sock_data(self.req)

    def handle_write(self):
        try:
            self.sock.sendall(self.data)
        except socket.error:
            pass
        self.webqq.event(WebQQHeartbeatEvent(self), self.delay)
        self._writable = False

    def prepare(self):
        """
        now = time.time()
        if self.webqq.start_time == self.webqq.hb_last_time or\
           now - self.webqq.hb_last_time >= 5:
            self.webqq.hb_last_time = now
            return HandlerReady()
        self._writeable = True
        """
        return HandlerReady()

    def is_readable(self):
        return False

    def is_writable(self):
        with self.lock:
            return self.sock and self.data and self._writable

class PollHandler(WebQQHandler ):
    """ 获取消息 """
    def setup(self, delay = 0):
        self.delay = delay
        url = "http://d.web2.qq.com/channel/poll2"
        params = [("r", '{"clientid":"%s", "psessionid":"%s",'
                   '"key":0, "ids":[]}' % (self.webqq.clientid,
                                           self.webqq.psessionid)),
                  ("clientid", self.webqq.clientid),
                  ("psessionid", self.webqq.psessionid)]
        self.method = "POST"
        self.req = http_sock.make_request(url, params, self.method)
        self.req.add_header("Referer", "http://d.web2.qq.com/proxy.html?v="
                            "20110331002&callback=1&id=2")
        self.sock, self.data = http_sock.make_http_sock_data(self.req)

    def handle_write(self):
        self._writable = False
        try:
            self.sock.sendall(self.data)
        except socket.error:
            pass
        else:
            self._readable = True
        self.webqq.event(WebQQPollEvent(self), self.delay)

    def handle_read(self):
        self._readable = False
        resp = http_sock.make_response(self.sock, self.req, self.method)
        tmp = resp.read()
        try:
            data = json.loads(tmp)
            self.webqq.event(WebQQMessageEvent(data, self))
        except ValueError:
            pass

    def is_writable(self):
        with self.lock:
            return self.sock and self.data and self._writable


class WebQQ(object):
    """ WebQQ
    :param :qid QQ号
    :param :event_queue pyxmpp2时间队列"""
    def __init__(self, qid, event_queue):
        self.logger = get_logger()
        self.qid = qid
        self.aid = 1003903
        self.clientid = random.randrange(11111111, 99999999)
        self.msg_id = random.randrange(1111111, 99999999)
        self.group_map = {}      # 群映射
        self.group_m_map = {}    # 群到群成员的映射
        self.uin_qid_map = {}    # uin 到 qq号的映射
        self.check_code = None
        self.skey = None
        self.ptwebqq = None
        self.require_check = False
        self.QUIT = False
        self.last_msg = {}
        self.event_queue = event_queue
        self.check_data = None           # CheckHanlder返回的数据
        self.blogin_data = None          # 登录前返回的数据
        self.rc = 1
        self.start_time = time.time()
        self.hb_last_time = self.start_time
        self.poll_last_time = self.start_time
        self._helper = HttpHelper()

    def event(self, event, delay = 0):
        """ timeout可以延迟将事件放入事件队列 """
        if delay:
            target = partial(self.put_delay_event, self.event_queue, event, delay)
            t = threading.Thread(target = target)
            t.setDaemon(True)
            t.start()
        else:
            self.event_queue.put(event)

    def put_delay_event(self, queue,event, delay):
        """ 应当放入线程中 """
        time.sleep(delay)
        queue.put(event)

    def ptui_checkVC(self, r, vcode, uin):
        """ 处理检查的回调 返回三个值 """
        if int(r) == 0:
            self.logger.info("Check Ok")
            self.check_code = vcode
        else:
            self.logger.warn("Check Error")
            self.check_code = self.get_check_img(vcode)
            self.require_check = True
        return r, self.check_code, uin

    def get_check_img(self, vcode):
        """ 获取验证图片 """
        url = "https://ssl.captcha.qq.com/getimage"
        params = [("aid", self.aid), ("r", random.random()),
                  ("uin", self.qid)]
        helper = HttpHelper(url, params, jar = http_sock.cookiejar)
        res = helper.open()
        path = tempfile.mktemp()
        fp = open(path, 'wb')
        fp.write(res.read())
        fp.close()
        res = upload_file("check.jpg", path)
        print res.geturl()
        check_code = None
        while not check_code:
            check_code = raw_input("打开上面连接输出图片上的验证码: ")
        return check_code.strip()

    def handle_pwd(self, password):
        """ 根据检查返回结果,调用回调生成密码和保存验证码 """
        r, self._vcode, huin = eval("self." + self.check_data.rstrip(";"))
        pwd = md5(md5(password).digest() + huin).hexdigest().upper()
        return md5(pwd + self._vcode).hexdigest().upper()

    def ptuiCB(self, scode, r, url, status, msg, nickname = None):
        """ 模拟JS登录之前的回调, 保存昵称 """
        if int(scode) == 0:
            self.logger.info("Get ptwebqq Ok")
            self.skey = http_sock.cookie['.qq.com']['/']['skey'].value
            self.ptwebqq = http_sock.cookie['.qq.com']['/']['ptwebqq'].value
            self.logined = True
        else:
            self.logger.warn("Get ptwebqq Error")
        if nickname:
            self.nickname = nickname

    def before_login(self, pwd):
        password = self.handle_pwd(pwd)
        t = 1 if self.require_check else 1
        params = [("u",self._qid), ("p",password),
                  ("verifycode", self._vcode), ("webqq_type",10),
                  ("remember_uin", 1),("login2qq",1),
                  ("aid", self._aid), ("u1", "http://www.qq.com"), ("h", 1),
                  ("ptredirect", 0), ("ptlang", 2052), ("from_ui", 1),
                  ("pttype", 1), ("dumy", ""), ("fp", "loginerroralert"),
                  ("mibao_css","m_webqq"), ("t",t),
                  ("g",1), ("js_type",0), ("js_ver", 10021)]
        url = "https://ssl.ptlogin2.qq.com/login"
        self._helper.change(url, params)
        self._helper.add_header("Referer",
                                "https://ui.ptlogin2.qq.com/cgi-bin/login?"
                                "target=self&style=5&mibao_css=m_webqq&app"
                                "id=1003903&enable_qlogin=0&no_verifyimg=1"
                                "&s_url=http%3A%2F%2Fweb.qq.com%2Floginpro"
                                "xy.html&f_url=log")
        res = self._helper.open()
        output = res.read()
        eval("self."+output.strip().rstrip(";"))
        self.logger.debug(output)

    def login(self, pwd):
        """ 利用前几步生成的数据进行登录
        :接口返回示例
            {u'retcode': 0,
            u'result': {
                'status': 'online', 'index': 1075,
                'psessionid': '', u'user_state': 0, u'f': 0,
                u'uin': 1685359365, u'cip': 3673277226,
                u'vfwebqq': u'', u'port': 43332}}
            保存result中的psessionid和vfwebqq供后面接口调用
        """

        self.before_login(pwd)
        url = "http://d.web2.qq.com/channel/login2"
        params = [("r", '{"status":"online","ptwebqq":"%s","passwd_sig":"",'
                   '"clientid":"%d", "psessionid":null}'\
                   % (self.ptwebqq, self.clientid)),
                  ("clientid", self.clientid),
                  ("psessionid", "null")
                  ]
        self._helper.change(url, params, "POST")
        self._helper.add_header("Referer", "http://d.web2.qq.com/proxy.html?"
                                "v=20110331002&callback=1&id=3")
        res = self._helper.open()
        data = json.loads(res.read())
        self.vfwebqq = data.get("result", {}).get("vfwebqq")
        self.psessionid = data.get("result", {}).get("psessionid")
        self.logger.debug(data)
        if data.get("retcode") == 0:
            self.logger.info("Login success")
        else:
            self.logger.warn("Login Error")

        self.mainloop()

    def mainloop(self):
        """ 主循环 """
        if self.logined:
            heartbeat = threading.Thread(name="heartbeat", target=self.heartbeat)
            heartbeat.setDaemon(True)
            heartbeat.start()
            self.get_group_members()
            self.poll()

    def get_group_map(self):
        """ 获取群映射列表 """
        self.logger.info("Get Group List")
        url = "http://s.web2.qq.com/api/get_group_name_list_mask2"
        params = [("r", '{"vfwebqq":"%s"}' % self.vfwebqq),]
        self._helper.change(url, params, "POST")
        self._helper.add_header("Origin", "http://s.web2.qq.com")
        self._helper.add_header("Referer", "http://s.web2.qq.com/proxy.ht"
                                "ml?v=20110412001&callback=1&id=1")

        res = self._helper.open()
        data = json.loads(res.read())
        group_map = {}
        if data.get("retcode") == 0:
            group_list = data.get("result", {}).get("gnamelist", [])
            for group in group_list:
                gcode = group.get("code")
                group_map[gcode] = group

        self.group_map = group_map
        return group_map

    def get_group_members(self):
        """ 根据群code获取群列表 """
        group_map = self.get_group_map()
        self.logger.info("Fetch group members")
        group_m_map = {}
        for gcode in group_map:
            url = "http://s.web2.qq.com/api/get_group_info_ext2"
            params = [("gcode", gcode),("vfwebqq", self.vfwebqq),
                    ("t", int(time.time()))]
            self._helper.change(url, params)
            self._helper.add_header("Referer", "http://d.web2.qq.com/proxy."
                                    "html?v=20110331002&callback=1&id=3")
            res = self._helper.open()
            info = json.loads(res.read())
            members = info.get("result", {}).get("minfo", [])
            group_m_map[gcode] = {}
            for m in members:
                uin = m.get("uin")
                group_m_map[gcode][uin] = m

            cards = info.get("result", {}).get("cards", [])
            for card in cards:
                uin = card.get("muin")
                group_name = card.get("card")
                group_m_map[gcode][uin]["nick"] = group_name

        self.group_m_map = group_m_map
        return group_m_map

    def get_qid_with_uin(self, uin):
        """ 根据uin获取QQ号 """
        url = "http://s.web2.qq.com/api/get_friend_uin2"
        params = [("tuin", uin), ("verifysession", ""),("type",4),
                  ("code", ""), ("vfwebqq", self.vfwebqq),
                  ("t", time.time())]
        self._helper.change(url, params)
        self._helper.add_header("Referer", "http://d.web2.qq.com/proxy."
                                "html?v=20110331002&callback=1&id=3")
        res = self._helper.open()
        data = res.read()
        if data:
            info = json.loads(data)
            if info.get("retcode") == 0:
                return info.get("result", {}).get("account")

    def send_group_msg(self, group_uin, content):
        if content != self.last_msg.get(group_uin)  :
            self.last_msg[group_uin] = content
            gid = self.group_map.get(group_uin).get("gid")
            content = [content,["font",
                    {"name":"宋体", "size":10, "style":[0,0,0],
                        "color":"000000"}]]
            r = {"group_uin": gid, "content": json.dumps(content),
                "msg_id": self.msg_id, "clientid": self.clientid,
                "psessionid": self.psessionid}
            self.msg_id += 1
            url = "http://d.web2.qq.com/channel/send_qun_msg2"
            params = [("r", json.dumps(r)), ("sessionid", self.psessionid),
                    ("clientid", self.clientid)]
            helper = HttpHelper(url, params, "POST")
            helper.add_header("Referer", "http://d.web2.qq.com/proxy.html")
            helper.open()

    def get_group_msg_img(self, uin, info):
        """ 获取消息中的图片 """
        name = info.get("name")
        file_id = info.get("file_id")
        key = info.get("key")
        server = info.get("server")
        ip, port = server.split(":")
        gid = self.group_map.get(uin, {}).get("gid")
        url = "http://web2.qq.com/cgi-bin/get_group_pic"
        params = [("type", 0), ("gid", gid), ("uin", uin),("rip", ip),
                  ("rport", port), ("fid", file_id), ("pic", name),
                  ("vfwebqq", self.vfwebqq), ("t", time.time())]
        helper = HttpHelper(url, params)
        helper.add_header("Referer", "http://web2.qq.com/")
        return helper.open()

    def get_group_name(self, gcode):
        """ 根据gcode获取群名 """
        return self.group_map.get(gcode, {}).get("name")

    def get_group_member_nick(self, gcode, uin):
        return self.group_m_map.get(gcode, {}).get(uin, {}).get("nick")
