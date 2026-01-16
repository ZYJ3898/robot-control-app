# -*- coding: GBK -*-
"""
robot_mobile_app.py
手机版机器人调试控制应用
基于Kivy框架，可在Android/iOS设备上运行
"""

from kivy.app import App
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.stacklayout import StackLayout
from kivy.uix.scrollview import ScrollView
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.togglebutton import ToggleButton
from kivy.uix.dropdown import DropDown
from kivy.uix.spinner import Spinner
from kivy.uix.switch import Switch
from kivy.uix.slider import Slider
from kivy.uix.popup import Popup
from kivy.uix.modalview import ModalView
from kivy.uix.progressbar import ProgressBar
from kivy.uix.tabbedpanel import TabbedPanel, TabbedPanelItem
from kivy.uix.accordion import Accordion, AccordionItem
from kivy.uix.carousel import Carousel
from kivy.uix.image import Image
from kivy.graphics import Color, Rectangle, Line, Ellipse
from kivy.core.window import Window
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.utils import get_color_from_hex
from kivy.properties import StringProperty, BooleanProperty, NumericProperty, ObjectProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.relativelayout import RelativeLayout
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.anchorlayout import AnchorLayout
from kivy.uix.pagelayout import PageLayout

import socket
import threading
import time
from datetime import datetime
import json
import os
from pathlib import Path

# 机器人协议类（与桌面版相同）
class RobotProtocol:
    """机器人协议处理类（支持ID控制）"""
    
    @staticmethod
    def calculate_checksum(data_bytes):
        """计算校验和：从帧长开始到校验前一个字节的和，取低8位"""
        if not data_bytes:
            return 0
        
        # 从帧长开始（跳过帧头AA 55）
        if len(data_bytes) >= 2 and data_bytes[0] == 0xAA and data_bytes[1] == 0x55:
            checksum_bytes = data_bytes[2:]
        else:
            checksum_bytes = data_bytes
        
        # 计算校验和（不包括校验字节本身）
        checksum = 0
        for byte in checksum_bytes:
            checksum = (checksum + byte) & 0xFF  # 只保留低8位
        
        return checksum
    
    @staticmethod
    def create_movement_command(direction, id_byte=0x00):
        """创建运动控制指令
        direction: 1=前进, 2=后退, 3=左转, 4=右转, 5=刹车, 6=停止
        id_byte: 0x00=整个小车, 0x01-0x04=单个轮毂
        """
        commands = {
            1: 0x01,  # 前进
            2: 0x02,  # 后退
            3: 0x03,  # 左转
            4: 0x04,  # 右转
            5: 0x05,  # 刹车
            6: 0x06,  # 停止
        }
        
        if direction not in commands:
            return None
            
        # 构建指令数据：帧长(04) 类型(80) ID字节 方向字节
        frame_data = b"\x04\x80" + bytes([id_byte]) + bytes([commands[direction]])
        
        # 计算校验和
        checksum = RobotProtocol.calculate_checksum(b"\xAA\x55" + frame_data)
        
        # 完整指令：AA 55 + 指令数据 + 校验和
        command = b"\xAA\x55" + frame_data + bytes([checksum])
        return command
    
    @staticmethod
    def create_speed_command(speed_rpm, accel_time=0, id_byte=0x00):
        """创建速度设置指令
        speed_rpm: 速度值 (0-115) - 单字节
        accel_time: 加速时间 (0-255) - 单位0.1ms
        id_byte: 0x00=整个小车, 0x01-0x04=单个轮毂
        格式：AA 55 07 81 01 [ID] [速度] [加速时间] (校验)
        """
        # 限制速度范围
        speed_rpm = max(0, min(115, int(speed_rpm)))
        
        # 限制加速时间范围
        accel_time = max(0, min(255, int(accel_time)))
        
        # 构建指令数据：帧长(07) 类型(81) 子类型(01) ID字节 速度字节 加速时间字节
        frame_data = b"\x07\x81\x01" + bytes([id_byte]) + bytes([speed_rpm]) + bytes([accel_time])
        
        # 计算校验和
        checksum = RobotProtocol.calculate_checksum(b"\xAA\x55" + frame_data)
        
        # 完整指令
        command = b"\xAA\x55" + frame_data + bytes([checksum])
        return command
    
    @staticmethod
    def create_angle_command(angle_degrees, id_byte=0x00):
        """创建角度设置指令
        angle_degrees: 角度值 (0 to 180.0) - 单字节
        id_byte: 固定为0x00
        格式：AA 55 07 81 02 00 [角度] 00 (校验)
        """
        # 限制角度范围
        angle_degrees = max(0.0, min(180.0, float(angle_degrees)))
        
        # 将0-180的角度映射到0-255的字节
        angle_byte = int(angle_degrees * 180.0 / 180.0)
        angle_byte = max(0, min(255, angle_byte))
        
        # 构建指令数据：帧长(07) 类型(81) 子类型(02) ID字节(00) 角度字节 加速时间(00)
        frame_data = b"\x07\x81\x02" + bytes([id_byte]) + bytes([angle_byte]) + b"\x00"
        
        # 计算校验和
        checksum = RobotProtocol.calculate_checksum(b"\xAA\x55" + frame_data)
        
        # 完整指令
        command = b"\xAA\x55" + frame_data + bytes([checksum])
        return command
    
    @staticmethod
    def decode_angle_from_byte(angle_byte):
        """从字节值解码角度
        angle_byte: 字节值 (0-255)
        返回：角度值 (0 to 180.0)
        """
        return angle_byte * 180.0 / 180.0
    
    @staticmethod
    def format_hex(data_bytes):
        """将字节数据格式化为十六进制字符串"""
        return ' '.join([f'{b:02X}' for b in data_bytes])

# TCP客户端类
class TCPClient:
    """TCP客户端类"""
    
    def __init__(self, on_receive_callback=None):
        self.socket = None
        self.is_connected = False
        self.receive_thread = None
        self.receive_callback = on_receive_callback
        self.host = "192.168.0.12"
        self.port = 12345
        
    def set_callback(self, callback):
        """设置数据接收回调函数"""
        self.receive_callback = callback
        
    def connect(self, host, port):
        """连接到TCP服务器"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5)  # 连接超时5秒
            self.socket.connect((host, port))
            self.socket.settimeout(0.5)  # 接收超时0.5秒
            self.is_connected = True
            self.host = host
            self.port = port
            
            # 启动接收线程
            self.receive_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self.receive_thread.start()
            
            return True, "连接成功"
        except socket.timeout:
            return False, "连接超时"
        except ConnectionRefusedError:
            return False, "连接被拒绝"
        except Exception as e:
            return False, f"连接失败: {str(e)}"
    
    def disconnect(self):
        """断开连接"""
        if self.socket:
            self.is_connected = False
            try:
                self.socket.close()
            except:
                pass
            self.socket = None
    
    def send_data(self, data_bytes):
        """发送数据"""
        if not self.is_connected or not self.socket:
            return False, "未连接"
            
        try:
            self.socket.sendall(data_bytes)
            return True, "发送成功"
        except Exception as e:
            self.is_connected = False
            return False, f"发送失败: {str(e)}"
    
    def _receive_loop(self):
        """接收数据循环"""
        while self.is_connected and self.socket:
            try:
                data = self.socket.recv(1024)
                if data and self.receive_callback:
                    self.receive_callback(data)
            except socket.timeout:
                continue
            except:
                break

# 自定义按钮类
class RoundedButton(ButtonBehavior, BoxLayout):
    text = StringProperty('')
    bg_color = StringProperty('#2196F3')
    text_color = StringProperty('#FFFFFF')
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'horizontal'
        self.size_hint = (None, None)
        self.height = dp(50)
        self.width = dp(120)
        
        with self.canvas.before:
            Color(*get_color_from_hex(self.bg_color))
            self.rect = Rectangle(pos=self.pos, size=self.size)
            
        self.bind(pos=self._update_rect, size=self._update_rect)
        
        self.label = Label(
            text=self.text,
            color=get_color_from_hex(self.text_color),
            font_size=sp(18),
            bold=True
        )
        self.add_widget(self.label)
    
    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

# 自定义文本框
class RoundedTextInput(TextInput):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.background_normal = ''
        self.background_active = ''
        self.background_color = get_color_from_hex('#FFFFFF')
        self.foreground_color = get_color_from_hex('#333333')
        self.font_size = sp(16)
        self.multiline = False
        self.padding = [dp(10), dp(10)]
        
        with self.canvas.before:
            Color(*get_color_from_hex('#E0E0E0'))
            self.rect = Rectangle(pos=self.pos, size=self.size)
            
        self.bind(pos=self._update_rect, size=self._update_rect)
    
    def _update_rect(self, instance, value):
        self.rect.pos = instance.pos
        self.rect.size = instance.size

# 主应用界面
class RobotMobileApp(BoxLayout):
    """手机版机器人控制应用主界面"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = 'vertical'
        self.spacing = dp(5)
        self.padding = [dp(10), dp(10), dp(10), dp(10)]
        
        # 创建TCP客户端
        self.tcp_client = TCPClient(self.on_data_received)
        
        # 初始化变量
        self.id_selection = 0  # 0=整个小车
        self.current_speed = 70  # 默认速度
        self.current_angle = 90  # 默认角度
        self.accel_time = 0  # 加速时间
        
        # 连接状态
        self.connection_status = "未连接"
        
        # 创建界面
        self.create_ui()
        
        # 启动定时器更新状态
        Clock.schedule_interval(self.update_status, 0.5)
    
    def create_ui(self):
        """创建用户界面"""
        # 标题
        title_label = Label(
            text='机器人调试控制',
            font_size=sp(24),
            bold=True,
            color=get_color_from_hex('#2196F3'),
            size_hint=(1, None),
            height=dp(60)
        )
        self.add_widget(title_label)
        
        # 创建滚动视图
        scroll_view = ScrollView(size_hint=(1, 1))
        main_layout = BoxLayout(orientation='vertical', size_hint=(1, None))
        main_layout.bind(minimum_height=main_layout.setter('height'))
        
        # 连接面板
        self.create_connection_panel(main_layout)
        
        # ID选择面板
        self.create_id_panel(main_layout)
        
        # 运动控制面板
        self.create_movement_panel(main_layout)
        
        # 速度控制面板
        self.create_speed_panel(main_layout)
        
        # 角度控制面板
        self.create_angle_panel(main_layout)
        
        # 监控面板
        self.create_monitor_panel(main_layout)
        
        # 添加到滚动视图
        scroll_view.add_widget(main_layout)
        self.add_widget(scroll_view)
    
    def create_connection_panel(self, parent):
        """创建连接面板"""
        # 连接框架
        conn_layout = BoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=dp(150),
            spacing=dp(5)
        )
        
        # 标题
        conn_title = Label(
            text='TCP连接设置',
            font_size=sp(18),
            bold=True,
            color=get_color_from_hex('#333333'),
            size_hint=(1, None),
            height=dp(30)
        )
        conn_layout.add_widget(conn_title)
        
        # IP地址输入
        ip_layout = BoxLayout(orientation='horizontal', size_hint=(1, None), height=dp(40))
        ip_layout.add_widget(Label(text='服务器IP:', size_hint=(0.3, 1)))
        self.ip_input = RoundedTextInput(
            text='192.168.0.12',
            size_hint=(0.7, 1)
        )
        ip_layout.add_widget(self.ip_input)
        conn_layout.add_widget(ip_layout)
        
        # 端口输入
        port_layout = BoxLayout(orientation='horizontal', size_hint=(1, None), height=dp(40))
        port_layout.add_widget(Label(text='端口号:', size_hint=(0.3, 1)))
        self.port_input = RoundedTextInput(
            text='12345',
            size_hint=(0.7, 1)
        )
        port_layout.add_widget(self.port_input)
        conn_layout.add_widget(port_layout)
        
        # 连接按钮
        button_layout = BoxLayout(orientation='horizontal', size_hint=(1, None), height=dp(50), spacing=dp(10))
        
        self.connect_btn = Button(
            text='连接',
            background_color=get_color_from_hex('#4CAF50'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(18),
            bold=True,
            size_hint=(0.5, 1)
        )
        self.connect_btn.bind(on_press=self.connect_server)
        
        self.disconnect_btn = Button(
            text='断开',
            background_color=get_color_from_hex('#F44336'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(18),
            bold=True,
            size_hint=(0.5, 1),
            disabled=True
        )
        self.disconnect_btn.bind(on_press=self.disconnect_server)
        
        button_layout.add_widget(self.connect_btn)
        button_layout.add_widget(self.disconnect_btn)
        conn_layout.add_widget(button_layout)
        
        # 状态显示
        self.status_label = Label(
            text='状态: 未连接',
            font_size=sp(16),
            color=get_color_from_hex('#F44336'),
            size_hint=(1, None),
            height=dp(30)
        )
        conn_layout.add_widget(self.status_label)
        
        parent.add_widget(conn_layout)
    
    def create_id_panel(self, parent):
        """创建ID选择面板"""
        # ID选择框架
        id_layout = BoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=dp(100),
            spacing=dp(5)
        )
        
        # 标题
        id_title = Label(
            text='ID选择 (0=整个小车, 1-4=单个轮毂)',
            font_size=sp(16),
            bold=True,
            color=get_color_from_hex('#333333'),
            size_hint=(1, None),
            height=dp(30)
        )
        id_layout.add_widget(id_title)
        
        # ID选择按钮
        id_button_layout = GridLayout(cols=5, size_hint=(1, None), height=dp(50), spacing=dp(5))
        
        id_options = [
            ('整个小车\n(ID=0)', 0),
            ('轮毂1\n(ID=1)', 1),
            ('轮毂2\n(ID=2)', 2),
            ('轮毂3\n(ID=3)', 3),
            ('轮毂4\n(ID=4)', 4)
        ]
        
        self.id_buttons = []
        for text, id_val in id_options:
            btn = ToggleButton(
                text=text,
                group='id_group',
                font_size=sp(12),
                size_hint=(1, 1)
            )
            btn.id_value = id_val
            btn.bind(on_press=self.select_id)
            
            if id_val == 0:
                btn.state = 'down'
            
            id_button_layout.add_widget(btn)
            self.id_buttons.append(btn)
        
        id_layout.add_widget(id_button_layout)
        
        # ID显示
        self.id_display = Label(
            text='当前ID: 0x00 (整个小车)',
            font_size=sp(14),
            color=get_color_from_hex('#2196F3'),
            size_hint=(1, None),
            height=dp(20)
        )
        id_layout.add_widget(self.id_display)
        
        parent.add_widget(id_layout)
    
    def create_movement_panel(self, parent):
        """创建运动控制面板"""
        # 运动控制框架
        move_layout = BoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=dp(250),
            spacing=dp(5)
        )
        
        # 标题
        move_title = Label(
            text='运动控制',
            font_size=sp(18),
            bold=True,
            color=get_color_from_hex('#333333'),
            size_hint=(1, None),
            height=dp(30)
        )
        move_layout.add_widget(move_title)
        
        # 运动按钮网格
        move_grid = GridLayout(cols=3, rows=3, size_hint=(1, None), height=dp(180), spacing=dp(5))
        
        # 第一行：前进按钮
        forward_btn = Button(
            text='前进',
            background_color=get_color_from_hex('#4CAF50'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(16),
            bold=True
        )
        forward_btn.bind(on_press=lambda x: self.send_movement_command(1))
        move_grid.add_widget(forward_btn)
        
        # 第二行：左转、停止、右转
        left_btn = Button(
            text='左转',
            background_color=get_color_from_hex('#2196F3'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(16),
            bold=True
        )
        left_btn.bind(on_press=lambda x: self.send_movement_command(3))
        move_grid.add_widget(left_btn)
        
        stop_btn = Button(
            text='停止',
            background_color=get_color_from_hex('#FF9800'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(16),
            bold=True
        )
        stop_btn.bind(on_press=lambda x: self.send_movement_command(6))
        move_grid.add_widget(stop_btn)
        
        right_btn = Button(
            text='右转',
            background_color=get_color_from_hex('#2196F3'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(16),
            bold=True
        )
        right_btn.bind(on_press=lambda x: self.send_movement_command(4))
        move_grid.add_widget(right_btn)
        
        # 第三行：后退按钮
        backward_btn = Button(
            text='后退',
            background_color=get_color_from_hex('#4CAF50'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(16),
            bold=True
        )
        backward_btn.bind(on_press=lambda x: self.send_movement_command(2))
        move_grid.add_widget(backward_btn)
        
        # 第四行：刹车按钮
        brake_btn = Button(
            text='刹车',
            background_color=get_color_from_hex('#F44336'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(16),
            bold=True
        )
        brake_btn.bind(on_press=lambda x: self.send_movement_command(5))
        move_grid.add_widget(brake_btn)
        
        move_layout.add_widget(move_grid)
        
        # 运动指令说明
        move_desc = Label(
            text='指令: AA 55 04 80 [ID] [方向]',
            font_size=sp(12),
            color=get_color_from_hex('#666666'),
            size_hint=(1, None),
            height=dp(30)
        )
        move_layout.add_widget(move_desc)
        
        parent.add_widget(move_layout)
    
    def create_speed_panel(self, parent):
        """创建速度控制面板"""
        # 速度控制框架
        speed_layout = BoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=dp(200),
            spacing=dp(5)
        )
        
        # 标题
        speed_title = Label(
            text='速度设置',
            font_size=sp(18),
            bold=True,
            color=get_color_from_hex('#333333'),
            size_hint=(1, None),
            height=dp(30)
        )
        speed_layout.add_widget(speed_title)
        
        # 速度滑块
        speed_slider_layout = BoxLayout(orientation='vertical', size_hint=(1, None), height=dp(80))
        
        speed_slider_layout.add_widget(Label(
            text=f'速度值: {self.current_speed} RPM (0-115)',
            font_size=sp(14),
            size_hint=(1, None),
            height=dp(20)
        ))
        
        self.speed_slider = Slider(
            min=0,
            max=115,
            value=self.current_speed,
            size_hint=(1, None),
            height=dp(30)
        )
        self.speed_slider.bind(value=self.on_speed_changed)
        speed_slider_layout.add_widget(self.speed_slider)
        
        # 速度值显示
        self.speed_display = Label(
            text=f'当前: {self.current_speed} RPM (字节: 0x{self.current_speed:02X})',
            font_size=sp(14),
            color=get_color_from_hex('#2196F3'),
            size_hint=(1, None),
            height=dp(30)
        )
        speed_slider_layout.add_widget(self.speed_display)
        
        speed_layout.add_widget(speed_slider_layout)
        
        # 加速时间设置
        accel_layout = BoxLayout(orientation='horizontal', size_hint=(1, None), height=dp(50))
        accel_layout.add_widget(Label(text='加速时间 (0-255):', size_hint=(0.5, 1)))
        
        self.accel_input = RoundedTextInput(
            text='0',
            size_hint=(0.3, 1)
        )
        accel_layout.add_widget(self.accel_input)
        
        # 设置速度按钮
        set_speed_btn = Button(
            text='设置',
            background_color=get_color_from_hex('#2196F3'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(14),
            bold=True,
            size_hint=(0.2, 1)
        )
        set_speed_btn.bind(on_press=self.send_speed_command)
        accel_layout.add_widget(set_speed_btn)
        
        speed_layout.add_widget(accel_layout)
        
        # 快速速度按钮
        quick_speed_layout = GridLayout(cols=5, size_hint=(1, None), height=dp(40), spacing=dp(5))
        
        quick_speeds = [('0', 0), ('10', 10), ('40', 40), ('70', 70), ('115', 115)]
        
        for text, speed in quick_speeds:
            btn = Button(
                text=text,
                font_size=sp(12),
                size_hint=(1, 1)
            )
            btn.bind(on_press=lambda x, s=speed: self.set_quick_speed(s))
            quick_speed_layout.add_widget(btn)
        
        speed_layout.add_widget(quick_speed_layout)
        
        # 速度指令说明
        speed_desc = Label(
            text='指令: AA 55 07 81 01 [ID] [速度] [加速时间]',
            font_size=sp(12),
            color=get_color_from_hex('#666666'),
            size_hint=(1, None),
            height=dp(30)
        )
        speed_layout.add_widget(speed_desc)
        
        parent.add_widget(speed_layout)
    
    def create_angle_panel(self, parent):
        """创建角度控制面板"""
        # 角度控制框架
        angle_layout = BoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=dp(180),
            spacing=dp(5)
        )
        
        # 标题
        angle_title = Label(
            text='角度设置 (ID固定为0)',
            font_size=sp(18),
            bold=True,
            color=get_color_from_hex('#333333'),
            size_hint=(1, None),
            height=dp(30)
        )
        angle_layout.add_widget(angle_title)
        
        # 角度滑块
        angle_slider_layout = BoxLayout(orientation='vertical', size_hint=(1, None), height=dp(80))
        
        angle_slider_layout.add_widget(Label(
            text=f'角度值: {self.current_angle}° (0-180)',
            font_size=sp(14),
            size_hint=(1, None),
            height=dp(20)
        ))
        
        self.angle_slider = Slider(
            min=0,
            max=180,
            value=self.current_angle,
            size_hint=(1, None),
            height=dp(30)
        )
        self.angle_slider.bind(value=self.on_angle_changed)
        angle_slider_layout.add_widget(self.angle_slider)
        
        # 角度值显示
        angle_byte = int(self.current_angle * 180.0 / 180.0)
        self.angle_display = Label(
            text=f'当前: {self.current_angle}° (字节: 0x{angle_byte:02X})',
            font_size=sp(14),
            color=get_color_from_hex('#2196F3'),
            size_hint=(1, None),
            height=dp(30)
        )
        angle_slider_layout.add_widget(self.angle_display)
        
        angle_layout.add_widget(angle_slider_layout)
        
        # 设置角度按钮
        set_angle_btn = Button(
            text='设置角度',
            background_color=get_color_from_hex('#9C27B0'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(16),
            bold=True,
            size_hint=(1, None),
            height=dp(50)
        )
        set_angle_btn.bind(on_press=self.send_angle_command)
        angle_layout.add_widget(set_angle_btn)
        
        # 角度指令说明
        angle_desc = Label(
            text='指令: AA 55 07 81 02 00 [角度] 00',
            font_size=sp(12),
            color=get_color_from_hex('#666666'),
            size_hint=(1, None),
            height=dp(30)
        )
        angle_layout.add_widget(angle_desc)
        
        parent.add_widget(angle_layout)
    
    def create_monitor_panel(self, parent):
        """创建监控面板"""
        # 监控框架
        monitor_layout = BoxLayout(
            orientation='vertical',
            size_hint=(1, None),
            height=dp(300),
            spacing=dp(5)
        )
        
        # 标题
        monitor_title = Label(
            text='数据监控',
            font_size=sp(18),
            bold=True,
            color=get_color_from_hex('#333333'),
            size_hint=(1, None),
            height=dp(30)
        )
        monitor_layout.add_widget(monitor_title)
        
        # 创建选项卡
        tab_panel = TabbedPanel(size_hint=(1, 1), do_default_tab=False)
        
        # 发送数据选项卡
        send_tab = TabbedPanelItem(text='发送数据')
        send_layout = BoxLayout(orientation='vertical')
        
        # 发送数据文本框
        self.send_text = TextInput(
            readonly=True,
            font_size=sp(14),
            background_color=get_color_from_hex('#F5F5F5'),
            foreground_color=get_color_from_hex('#333333'),
            size_hint=(1, 1)
        )
        send_layout.add_widget(self.send_text)
        
        # 清空按钮
        clear_send_btn = Button(
            text='清空发送数据',
            background_color=get_color_from_hex('#607D8B'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(14),
            size_hint=(1, None),
            height=dp(40)
        )
        clear_send_btn.bind(on_press=self.clear_send_text)
        send_layout.add_widget(clear_send_btn)
        
        send_tab.add_widget(send_layout)
        tab_panel.add_widget(send_tab)
        
        # 接收数据选项卡
        recv_tab = TabbedPanelItem(text='接收数据')
        recv_layout = BoxLayout(orientation='vertical')
        
        # 接收数据文本框
        self.recv_text = TextInput(
            readonly=True,
            font_size=sp(14),
            background_color=get_color_from_hex('#F5F5F5'),
            foreground_color=get_color_from_hex('#333333'),
            size_hint=(1, 1)
        )
        recv_layout.add_widget(self.recv_text)
        
        # 清空按钮
        clear_recv_btn = Button(
            text='清空接收数据',
            background_color=get_color_from_hex('#607D8B'),
            color=get_color_from_hex('#FFFFFF'),
            font_size=sp(14),
            size_hint=(1, None),
            height=dp(40)
        )
        clear_recv_btn.bind(on_press=self.clear_recv_text)
        recv_layout.add_widget(clear_recv_btn)
        
        recv_tab.add_widget(recv_layout)
        tab_panel.add_widget(recv_tab)
        
        monitor_layout.add_widget(tab_panel)
        
        parent.add_widget(monitor_layout)
    
    def select_id(self, instance):
        """选择ID"""
        self.id_selection = instance.id_value
        
        id_names = {
            0: "整个小车",
            1: "轮毂1",
            2: "轮毂2",
            3: "轮毂3",
            4: "轮毂4"
        }
        
        self.id_display.text = f'当前ID: 0x{self.id_selection:02X} ({id_names.get(self.id_selection, "未知")})'
    
    def on_speed_changed(self, instance, value):
        """速度滑块变化"""
        self.current_speed = int(value)
        self.speed_display.text = f'当前: {self.current_speed} RPM (字节: 0x{self.current_speed:02X})'
    
    def on_angle_changed(self, instance, value):
        """角度滑块变化"""
        self.current_angle = int(value)
        angle_byte = int(self.current_angle * 180.0 / 180.0)
        self.angle_display.text = f'当前: {self.current_angle}° (字节: 0x{angle_byte:02X})'
    
    def connect_server(self, instance):
        """连接服务器"""
        host = self.ip_input.text
        port_text = self.port_input.text
        
        if not host or not port_text:
            self.show_popup("错误", "请输入服务器IP和端口号")
            return
            
        try:
            port = int(port_text)
        except ValueError:
            self.show_popup("错误", "端口号必须是数字")
            return
        
        # 更新状态
        self.status_label.text = "正在连接..."
        self.status_label.color = get_color_from_hex('#FF9800')
        
        # 连接服务器
        success, message = self.tcp_client.connect(host, port)
        
        if success:
            self.connection_status = "已连接"
            self.status_label.text = f"状态: 已连接 ({host}:{port})"
            self.status_label.color = get_color_from_hex('#4CAF50')
            
            self.connect_btn.disabled = True
            self.disconnect_btn.disabled = False
            
            self.log_send(f"连接到服务器: {host}:{port}")
            self.log_recv(f"连接成功: {message}")
        else:
            self.connection_status = "连接失败"
            self.status_label.text = f"状态: 连接失败"
            self.status_label.color = get_color_from_hex('#F44336')
            
            self.show_popup("连接失败", message)
            self.log_recv(f"连接失败: {message}")
    
    def disconnect_server(self, instance):
        """断开服务器连接"""
        self.tcp_client.disconnect()
        self.connection_status = "未连接"
        self.status_label.text = "状态: 未连接"
        self.status_label.color = get_color_from_hex('#F44336')
        
        self.connect_btn.disabled = False
        self.disconnect_btn.disabled = True
        
        self.log_send("断开服务器连接")
    
    def send_movement_command(self, direction):
        """发送运动控制命令"""
        if not self.tcp_client.is_connected:
            self.show_popup("未连接", "请先连接到服务器")
            return
            
        # 创建命令
        command = RobotProtocol.create_movement_command(direction, self.id_selection)
        if not command:
            self.show_popup("错误", "无效的运动命令")
            return
            
        # 发送命令
        success, message = self.tcp_client.send_data(command)
        
        if success:
            # 记录发送数据
            hex_str = RobotProtocol.format_hex(command)
            direction_names = {
                1: "前进", 2: "后退", 3: "左转", 
                4: "右转", 5: "刹车", 6: "停止"
            }
            direction_name = direction_names.get(direction, "未知")
            
            id_names = {
                0: "整个小车",
                1: "轮毂1",
                2: "轮毂2",
                3: "轮毂3",
                4: "轮毂4"
            }
            id_name = id_names.get(self.id_selection, f"ID={self.id_selection}")
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_send(f"[{timestamp}] {id_name} {direction_name}: {hex_str}")
        else:
            self.show_popup("发送失败", message)
    
    def send_speed_command(self, instance):
        """发送速度设置命令"""
        if not self.tcp_client.is_connected:
            self.show_popup("未连接", "请先连接到服务器")
            return
            
        try:
            # 获取加速时间
            accel_time = int(self.accel_input.text)
            
            # 验证输入
            if accel_time < 0 or accel_time > 255:
                self.show_popup("错误", "加速时间必须在0-255之间")
                return
                
        except ValueError:
            self.show_popup("错误", "请输入有效的数字")
            return
            
        # 创建命令
        command = RobotProtocol.create_speed_command(self.current_speed, accel_time, self.id_selection)
        
        # 发送命令
        success, message = self.tcp_client.send_data(command)
        
        if success:
            # 记录发送数据
            hex_str = RobotProtocol.format_hex(command)
            
            id_names = {
                0: "整个小车",
                1: "轮毂1",
                2: "轮毂2",
                3: "轮毂3",
                4: "轮毂4"
            }
            id_name = id_names.get(self.id_selection, f"ID={self.id_selection}")
            
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_send(f"[{timestamp}] {id_name} 设置速度: {self.current_speed}RPM, 加速时间: {accel_time}")
            self.log_send(f"       指令: {hex_str}")
        else:
            self.show_popup("发送失败", message)
    
    def send_angle_command(self, instance):
        """发送角度设置命令"""
        if not self.tcp_client.is_connected:
            self.show_popup("未连接", "请先连接到服务器")
            return
            
        # 创建命令 (角度设置ID固定为0x00)
        command = RobotProtocol.create_angle_command(self.current_angle, 0x00)
        
        # 发送命令
        success, message = self.tcp_client.send_data(command)
        
        if success:
            # 计算字节值
            angle_byte = int(self.current_angle * 180.0 / 180.0)
            
            # 记录发送数据
            hex_str = RobotProtocol.format_hex(command)
            timestamp = datetime.now().strftime("%H:%M:%S")
            self.log_send(f"[{timestamp}] 设置角度: {self.current_angle}° (字节: 0x{angle_byte:02X})")
            self.log_send(f"       指令: {hex_str}")
        else:
            self.show_popup("发送失败", message)
    
    def set_quick_speed(self, speed):
        """快速设置速度"""
        self.current_speed = speed
        self.speed_slider.value = speed
        self.on_speed_changed(None, speed)
        
        # 自动发送
        self.send_speed_command(None)
    
    def on_data_received(self, data):
        """接收到数据"""
        # 在主线程中更新UI
        Clock.schedule_once(lambda dt: self.process_received_data(data), 0)
    
    def process_received_data(self, data):
        """处理接收到的数据"""
        # 记录接收数据
        hex_str = RobotProtocol.format_hex(data)
        timestamp = datetime.now().strftime("%H:%M:%S")
        
        # 尝试解码响应
        decoded = self.decode_response(data)
        if decoded:
            self.log_recv(f"[{timestamp}] {decoded}")
        else:
            self.log_recv(f"[{timestamp}] 接收数据: {hex_str}")
    
    def decode_response(self, data):
        """尝试解码响应数据"""
        if len(data) < 6:
            return None
        
        # 检查帧头
        if data[0] != 0xAA or data[1] != 0x55:
            return None
        
        hex_str = RobotProtocol.format_hex(data)
        
        # 运动响应
        if len(data) == 6 and data[2] == 0x04 and data[3] == 0x80:
            direction_codes = {
                0x01: "前进确认",
                0x02: "后退确认",
                0x03: "左转确认",
                0x04: "右转确认",
                0x05: "刹车确认",
                0x06: "停止确认"
            }
            direction = data[5] if len(data) > 5 else 0
            
            # 获取ID
            id_byte = data[4] if len(data) > 4 else 0
            id_names = {
                0: "整个小车",
                1: "轮毂1",
                2: "轮毂2",
                3: "轮毂3",
                4: "轮毂4"
            }
            id_name = id_names.get(id_byte, f"ID={id_byte}")
            
            return f"运动响应: {id_name} {direction_codes.get(direction, '未知')}"
        
        # 速度设置响应
        elif len(data) == 8 and data[2] == 0x07 and data[3] == 0x81 and data[4] == 0x01:
            id_byte = data[5]
            speed = data[6]
            accel = data[7]
            
            id_names = {
                0: "整个小车",
                1: "轮毂1",
                2: "轮毂2",
                3: "轮毂3",
                4: "轮毂4"
            }
            id_name = id_names.get(id_byte, f"ID={id_byte}")
            
            return f"速度设置响应: {id_name} 速度={speed}RPM, 加速时间={accel}*0.1ms"
        
        # 角度设置响应
        elif len(data) == 8 and data[2] == 0x07 and data[3] == 0x81 and data[4] == 0x02:
            angle_byte = data[6]
            angle_degrees = RobotProtocol.decode_angle_from_byte(angle_byte)
            return f"角度设置响应: 角度={angle_degrees:.1f}° (字节: 0x{angle_byte:02X})"
        
        return None
    
    def log_send(self, message):
        """记录发送日志"""
        self.send_text.text += message + "\n"
        # 滚动到底部
        self.send_text.cursor = (0, len(self.send_text.text))
    
    def log_recv(self, message):
        """记录接收日志"""
        self.recv_text.text += message + "\n"
        # 滚动到底部
        self.recv_text.cursor = (0, len(self.recv_text.text))
    
    def clear_send_text(self, instance):
        """清空发送文本"""
        self.send_text.text = ""
    
    def clear_recv_text(self, instance):
        """清空接收文本"""
        self.recv_text.text = ""
    
    def show_popup(self, title, message):
        """显示弹出窗口"""
        content = BoxLayout(orientation='vertical', padding=dp(10), spacing=dp(10))
        content.add_widget(Label(text=message, font_size=sp(16)))
        
        btn = Button(
            text='确定',
            size_hint=(1, None),
            height=dp(50),
            background_color=get_color_from_hex('#2196F3')
        )
        
        popup = Popup(
            title=title,
            content=content,
            size_hint=(0.8, 0.4)
        )
        
        btn.bind(on_press=popup.dismiss)
        content.add_widget(btn)
        
        popup.open()
    
    def update_status(self, dt):
        """更新状态"""
        # 这里可以添加定期更新的状态信息
        pass

# 主应用
class RobotMobileAppMain(App):
    def build(self):
        # 设置窗口大小（针对手机屏幕）
        Window.size = (400, 700)
        
        # 设置应用标题
        self.title = "机器人调试控制"
        
        # 返回主界面
        return RobotMobileApp()

# 启动应用
if __name__ == '__main__':
    RobotMobileAppMain().run()