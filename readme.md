# Gumpy #

动态容器

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
          - MOD 为 python 模块的组件                         
      pkg_bdl        [PKG]
          - PKG 为 python 的包组件     
      zip_bdl.zip    [ZIP]
          - ZIP 为 zip 包，内部必须含一个完整同名的 python 包结构
      file_bdl       [MOD]
    >>> install mod_bdl
          - 安装 mod_bdl
    >>> install file_bdl
          - 安装 file_bdl
    >>> start mod_bdl
          - 启动 mod_bdl
    >>> start file_bdl
          - 启动 file_bdl
    >>> list
      file_bdl       [ACTIVE]       
      mod_bdl        [ACTIVE]
    >>> call file_bdl:SampleServiceA.foo()
          - 调用 file_bdl 组件中的 SampleServiceA 服务中的 foo 办法
    <mod_bdl.SampleServiceA object at 0x7f1210ddec90>
    
## Web console ##

内置简单的网页管理组件，plugins/console_server 组件，请输入下面指令启动：

    $ python -m gumpy
    Gumpy runtime console
    >>> install console_server
    >>> start console_server
    
启动后访问 http://localhost:3040 进入 WEB 控制台
