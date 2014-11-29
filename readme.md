# Gumpy #

动态容器用户指南，开发者请参考[开发指南](huacaya/devguide.md)

## 启动 ##

    $ python -m gumpy -p [plugins_dir]
    
上述代码启动 gumpy 模块，以 [plugins_dir] 目录为组件目录（默认为当前目录下的 plugins）

## 指令 ##

* repo - 列出在库组件
* list - 列出已安装组件
* install [在库组件] - 安装组件
* start [已安装插件] - 启动组件
* stop [已启动插件] - 停止组件
* call [插件]:[服务].foo() - 调用服务的接口

## 范例 ##

    $ python -m gumpy -p samples
    Gumpy runtime console
    >>> repo
      mod_bdl        [MOD]
          # MOD 为 python 模块的组件                         
      pkg_bdl        [PKG]
          # PKG 为 python 的包组件     
      zip_bdl.zip    [ZIP]
          # ZIP 为 zip 包，内部必须含一个完整同名的 python 包结构
      file_bdl       [MOD]
    >>> install mod_bdl
          # 安装 mod_bdl
    >>> install file_bdl
          # 安装 file_bdl
    >>> start mod_bdl
          # 启动 mod_bdl
    >>> start file_bdl
          # 启动 file_bdl
    >>> list
      file_bdl       [ACTIVE]       
      mod_bdl        [ACTIVE]
    >>> call file_bdl:SampleServiceA.foo()
          # 调用 file_bdl 组件中的 SampleServiceA 服务中的 foo 办法
    <mod_bdl.SampleServiceA object at 0x7f1210ddec90>
    
## Web console ##

内置简单的网页管理组件，plugins/web_console 组件，请输入下面指令启动：

    $ python -m gumpy
    Gumpy runtime console
    >>> install web_console
    >>> start web_console
    
启动后访问 http://localhost:3040 进入 WEB 控制台

## Configuration 配置 ##

每个组件都能够使用配置功能，可使用以下命令修改：

    >>> conf wsgi_serv port 8080
    
控制台会在每次修改配置后会触发对应组件的 on_configuration_changed 事件，该组件在改变端口后自动重启服务器。配置获取方式与事件处理代码详见 [wsgi_serv.py](plugins/wsgi_serv.py)。

## 协程任务 ##

协程任务代码示例详见[task_demo.py](plugins/task_demo.py)。其中要点：

1. 使用 task 装饰器定义协程任务
2. 在任务的循环最底层，使用 yield 确保调度切换
3. 在构造函数或者 on_start 中启动协程

加载示例组件：

    >>> install task_demo
          # 安装 task_demo
    >>> start task_demo
          # 启动 task_demo
          
触发 [message_task](plugins/task_demo.py#L16) 调度：

    >>> fireall on_message hello
          # 触发 on_message 事件，参数为 hello
    >>> step
          # 推进协程调度器，空行回车也执行该命令
          # 命令格式 step [n]，步长 n 默认为 1
    TaskDemo on_message: hello
    
          
触发 [counter_task](plugins/task_demo.py#L24) 调度：

    >>> step
    TaskDemo counter: 0
    
    
注意 step 一次只推进一个任务，多任务的场景下可能无法切确知道 step 何时触发：

    >>> fire task_demo on_message world
          # 触发 task_demo 组件的 on_message 事件，参数为 hello
    >>> step
    >>> step
    TaskDemo on_message: world
    >>> step 10
    TaskDemo counter: 1
    TaskDemo counter: 2
    TaskDemo counter: 3
    TaskDemo counter: 4
    TaskDemo counter: 5

协程属于被动式推动机制，如需独立于容器进行主动式调度，可直接在组件中使用线程，详见 [wsgi_serv.py](plugins/wsgi_serv.py)。