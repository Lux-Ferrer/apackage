# -*- coding: utf-8 -*-
"""应用入口。

用法：
    python app.py        # 本地开发服务器，http://127.0.0.1:5000
"""

from webapp import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
