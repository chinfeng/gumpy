# GumPY 指南（huacaya） #

通过建立一个 appserv 的最小原型，展示 gumpy 的各种特性。

## 准备工作 ##

以名字 huacaya 建立目录，所有组件都存放在此目录中。然后启动容器：

    $ python -m gumpy -p huacaya -a
    Gumpy runtime console
    >>>

启动参数 -p 用于制定组件库目录，-a 无阻塞运行模式。

*PS：gumpy 是以协程模式运行，阻塞模式（无参数 -a）需要手工调用 step 推动协程调度，无阻塞模式（带参数 -a）则在另一个线程中自动推动协程调度。*

此时组件库中尚未有任何组件，下面我们建立一个 WSGI 服务器。

## WSGI Server using thread mode ##

在标准库中有 wsgiref 模块，提供 WSGI 服务器的执行。我们使用这个模块建立一个基于线程池的 WSGI 服务器组件，命名为 [tserv](tserv.py)。

1. 首先新建文件 huacaya/tserv.py，此文件中加入代码：

		@service
		class WSGISevice(object):
		    ......

    当我们安装并启动 tserv 这个组件，这个 WSGIServer 就会成为一个常驻容器中的服务。

2. 对 wsgiref.simple_server 作一点改造，支持线程模式（详见[ThreadPoolWSGIServer](tserv.py#L12)）。

3. 在 [WSGIService.\_\_init\_\_](tserv.py#L38) 中启动服务器，并在 [WSGIService.on_stop](tserv.py#L56) 方法让组件停止的时候关闭 WSGI 服务器。

4. 实现分发 WSGI 应用的方法，使用 [bind](tserv.py#L61)/[unbind](tserv.py#L69) 方法，处理应用的登记和注销。应用的部分请参见下文的[第一个应用组件](#第一个应用组件)

    *PS：在 gumpy 中，bind/unbind 为动态机制，当其他服务中所提供的同一个字符串的服务，会自动触发 bind，之后如果服务关联的组件停止，会自动触发 unbind。本例中使用这种机制完成 WSGI 应用的登记和注销。*

5. 把请求路径的第一个目录作为应用选择器，分发给不同的 WSGI 应用进行后续处理，详见[WSGIService._wsgi_app](tserv.py#L76)。

6. 注意上述代码中，分别使用了 port 和 rootapp 两个配置。port 用于指定服务器端口，rootapp 用于配置主应用。我们使用一个事件[WSGIService.on_configuration_changed](tserv.py#L87)，处理这两个参数改变时的动作。

    *PS：事件是 gumpy 的一种内置机制，控制台使用命令“conf tserv port 8000”可改变 tserv 组件的 port 参数。每当参数改变时，控制台都会触发一个名为 [on_configuration_changed](../gumpy/console.py#L119) 的事件。如果使用代码控制 gumpy 容器，则可自行触发事件*

7. 代码完成后，可启动 tserv 组件：

        >>> install tserv
        >>> start tserv

    然后我们就可以在浏览器输入 http://localhost:8001 来访问。

## WSGI Server using coroutine mode ##

在 gumpy 容器可使用协程模式，我们可以在 [cserv.py](cserv.py) 中看到如何使用协程模式实现 WSGI 服务器。

1. 在所有的 gumpy 组件中，都有一个内置的成员“\_\_executor\_\_”，为整个容器的调度接口。从这个接口延伸出来可以就可以在代码中使用协程调度，详见[TaskPoolWSGIServer构造函数](cserv.py#L45)。

2. 接口传递给协程服务器的实现类[TaskPoolWSGIServer](cserv.py#L11)，即可使用 submit 方法提交协程任务，语法如下：

        executor.submit(func, [参数1], [参数2], ......)

    如在 [process_request](cserv.py#L24) 函数中，我们把提交线程池执行改成为由协程执行。

3. 我们开启另外一个线程，执行 [serve_forever](cserv.py#L27) 函数。如果我们在启动容器的时候，带了 -a 参数，那么内存中就存在 3 个线程：

    * 主线程，负责 gumpy console 的执行
    * gumpy 的自动推进线程，不停的推进协程调度（实现代码见 [gumpy/\_\_main\_\_.py](../gumpy/\_\_main\_\_.py#L35)
    * cserv:WSGIServer 中的 sock 线程

    处理流程是：由 serve_forever 启动的 sock 线程接受到客户端以后，就把这个处理操作提交给协程调度器，然后由 gumpy 的协程调度器负责处理。

4. 使用 [configuration](cserv.py#L42) 机制修改一下默认的端口号，这样协程和线程服务器就可以同时开启。同时我们需要区分我们的应用注册到哪个服务器，所以 bind 的规则也需要作调整，详见 [bind](cserv.py#L59) 配置。

5. 启动服务器：

        >>> install cserv
        >>> start cserv

好了，现在已经拥有了两个 WSGI 服务器，接下来我们可以编写第一个应用组件。

## 第一个应用组件 ##

我们使用了三方库 tornado 来实现一个简单的 WSGI 应用，请读者自行安装相关依赖库。

1. 使用 service 装饰器定义一个服务，见[firstapp.py](firstapp.py#L13)。

2. 使用 provide 装饰器定义服务匹配规则，见 [firstapp.py](firstapp.py#L14)。

3. provide 装饰器可以多次定义，这里我们希望同时给两个服务器提供应用，见[firstapp.py](firstapp.py#L15)

4. 在前面的服务器中，使用了 \_\_route\_\_ 作为应用的目录参数，可以指定自身的路径，见[firstapp.py](firstapp.py#L17)

5. 我们可以启动这个组件：

        >>> install firstapp
        >>> start firstapp

    然后我们可以使用 localhost:8001/firstapp 和 localhost:8002/firstapp 来访问这个应用了。

	*PS：当“stop firstapp”以后，就会在动态的环境下触发服务的 unbind，这样 firstapp 就无法访问了。*

*PS：可以看到，只要服务 provide 出去的东西是标准的 wsgi application 接口，就能动态绑定到服务器上。wsgi application 的上层何种应用框架，并无限制，所以我们可以在不同的 \_\_route\_\_ 上，提供 tornado、webpy、flask 甚至是 django 的集成，相互不影响，又能够动态装卸。*

# (未完待续) #

