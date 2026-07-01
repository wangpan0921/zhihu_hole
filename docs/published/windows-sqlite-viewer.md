# Windows 上如何查看 SQLite 数据库：工具安装和基本用法

很多 AI 生成的小网页应用，后台数据不会一开始就接 MySQL、PostgreSQL 这类服务型数据库，而是直接使用一个 SQLite 文件。

你在项目目录里可能会看到这些文件名：

```text
app.db
data.db
database.db
sqlite.db
dev.sqlite
db.sqlite3
```

它们本质上就是数据库文件。和 MySQL 不同，SQLite 通常不需要单独启动一个数据库服务。应用程序读写的就是这个 `.db`、`.sqlite`、`.sqlite3` 文件。

这篇文章解决一个很具体的问题：

> 在 Windows 系统上，拿到一个 SQLite 数据库文件后，应该用什么工具查看，怎么安装，怎么使用？

如果你只想快速看表和数据，优先用图形化工具。如果你要排查程序问题、复制 SQL、写脚本，再学一下命令行工具。

## 1. 先确认哪个文件是 SQLite 数据库

SQLite 数据库经常没有固定后缀。常见后缀有：

- `.db`
- `.sqlite`
- `.sqlite3`
- `.data`

但后缀不可靠。最简单的判断方式是：用 SQLite 工具能打开，并且能看到表结构。

如果你不确定项目里哪个文件是数据库，可以先在项目目录里搜索这些后缀。PowerShell 示例：

```powershell
Get-ChildItem -Recurse -File -Include *.db,*.sqlite,*.sqlite3
```

有些 Web 框架也会有默认习惯：

- Django 常见：`db.sqlite3`
- Flask / FastAPI 示例项目常见：`app.db`、`database.db`
- Electron 或本地桌面工具常见：放在用户目录、应用数据目录下

拿到数据库文件以后，建议先复制一份再查看。

例如把：

```text
database.db
```

复制成：

```text
database-copy.db
```

然后打开副本。这样即使误点了编辑、删除、保存，也不会影响应用正在使用的原始数据库。

## 2. 推荐工具一：DB Browser for SQLite

如果你是第一次查看 SQLite，最推荐从 DB Browser for SQLite 开始。

它的优点是：

- 免费、开源。
- Windows 上安装简单。
- 可以像 Excel 一样浏览表数据。
- 可以查看表结构、索引、触发器。
- 可以执行 SQL 查询。
- 可以导出 CSV，方便后续用 Excel 分析。

官方网站：

```text
https://sqlitebrowser.org/
```

下载页面：

```text
https://sqlitebrowser.org/dl/
```

### 安装 DB Browser for SQLite

打开下载页面后，选择 Windows 版本。大多数电脑选择 64-bit installer 即可。

下载到的文件名可能类似：

```text
DB.Browser.for.SQLite-版本号-win64.msi
```

双击安装，一路按提示继续即可。安装完成后，可以在开始菜单里搜索：

```text
DB Browser for SQLite
```

### 打开数据库文件

启动软件后：

1. 点击左上角 `Open Database`。
2. 选择你的 `.db`、`.sqlite` 或 `.sqlite3` 文件。
3. 打开后，先看上方几个常用标签页。

常见标签页含义：

- `Database Structure`：看数据库结构，例如有哪些表、每张表有哪些字段。
- `Browse Data`：像表格一样查看数据。
- `Execute SQL`：手写 SQL 查询。
- `Edit Pragmas`：查看和修改 SQLite 的一些底层设置，新手一般不用。

### 查看表数据

切到 `Browse Data` 标签页。

在 `Table` 下拉框里选择一张表，就能看到这张表里的数据。

常用操作：

- 点击列名排序。
- 在筛选框里输入关键字过滤。
- 调整底部分页或行数，查看更多记录。
- 右键单元格复制内容。

如果你只是想确认“用户表里有没有数据”“某条记录有没有写进去”，这个页面通常就够用了。

### 查看表结构

切到 `Database Structure` 标签页。

你会看到类似这样的信息：

- 表名。
- 字段名。
- 字段类型。
- 是否允许为空。
- 是否是主键。
- 索引。

例如一张用户表可能包含：

```text
id
username
email
created_at
```

排查程序问题时，表结构很重要。比如代码里写的是 `user_name`，数据库里实际字段叫 `username`，程序就可能报错。

### 执行 SQL 查询

切到 `Execute SQL` 标签页，可以输入 SQL。

例如查看用户表前 20 行：

```sql
SELECT * FROM users LIMIT 20;
```

按执行按钮后，下方会显示查询结果。

再比如按时间倒序查看最近的数据：

```sql
SELECT *
FROM users
ORDER BY created_at DESC
LIMIT 20;
```

如果你不确定有哪些表，可以先在 `Database Structure` 看表名，再复制表名来查询。

### 修改数据时要小心

DB Browser for SQLite 不只是查看工具，它也可以改数据。

如果你改了数据，通常需要点击 `Write Changes` 才会真正写回数据库文件。也就是说：

- 只是浏览、查询，一般不会改变数据库。
- 手动编辑表格内容、删除行、执行 `UPDATE` / `DELETE` / `INSERT`，就可能改变数据库。
- 点击 `Write Changes` 后，修改会落到文件里。

新手建议默认只打开数据库副本。确实要改原始数据库时，先备份。

## 3. 推荐工具二：SQLite 官方命令行 sqlite3

图形化工具适合查看数据，但开发者也应该会一点命令行。

SQLite 官方提供了 `sqlite3` 命令行工具。它适合：

- 快速确认一个数据库能否打开。
- 查看有哪些表。
- 查看建表语句。
- 执行一两句 SQL。
- 在脚本里自动导出数据。

官方网站下载页：

```text
https://www.sqlite.org/download.html
```

### 下载 sqlite3

打开下载页，找到 Windows 区域，下载命令行工具压缩包。文件名通常类似：

```text
sqlite-tools-win-x64-版本号.zip
```

下载后解压到一个固定目录，例如：

```text
C:\tools\sqlite
```

解压后里面会有：

```text
sqlite3.exe
sqldiff.exe
sqlite3_analyzer.exe
```

最常用的是 `sqlite3.exe`。

### 临时使用 sqlite3

打开 PowerShell，进入解压目录：

```powershell
cd C:\tools\sqlite
```

假设数据库文件在：

```text
D:\demo\database.db
```

可以这样打开：

```powershell
.\sqlite3.exe D:\demo\database.db
```

进入后会看到 `sqlite>` 提示符。

### 添加到 PATH

如果你希望在任意目录都能执行 `sqlite3`，可以把 `C:\tools\sqlite` 加到系统 PATH。

操作步骤：

1. 按 Win 键，搜索“环境变量”。
2. 打开“编辑系统环境变量”。
3. 点击“环境变量”。
4. 在用户变量里找到 `Path`，点击编辑。
5. 新增一项：`C:\tools\sqlite`。
6. 一路确定保存。
7. 重新打开 PowerShell。

验证：

```powershell
sqlite3 --version
```

能输出版本号，说明配置成功。

### 常用 sqlite3 命令

打开数据库：

```powershell
sqlite3 D:\demo\database.db
```

进入后查看所有表：

```sql
.tables
```

查看某张表的建表语句：

```sql
.schema users
```

让查询结果更适合人看：

```sql
.headers on
.mode column
```

查询数据：

```sql
SELECT * FROM users LIMIT 10;
```

退出：

```sql
.quit
```

注意：以点开头的是 sqlite3 自己的命令，例如 `.tables`、`.schema`、`.quit`。普通 SQL 语句通常以分号结尾。

### 用 sqlite3 导出 CSV

有时你想把查询结果导出成 CSV，再用 Excel 打开。

示例：

```sql
.headers on
.mode csv
.output users.csv
SELECT * FROM users;
.output stdout
```

这会在当前目录生成 `users.csv`。

如果数据里有中文，Excel 打开 CSV 时可能出现乱码。可以先用 VS Code 打开确认编码，或者在 Excel 里通过“数据”里的导入功能指定 UTF-8。

### 用 sqlite3 备份数据库

如果应用正在使用数据库，直接复制文件有时不够稳妥。SQLite 命令行提供了 `.backup`。

示例：

```powershell
sqlite3 D:\demo\database.db
```

进入后执行：

```sql
.backup D:/demo/database-backup.db
.quit
```

这样可以生成一个备份文件，再用图形化工具打开备份。

## 4. 推荐工具三：DBeaver

如果你平时还会连接 MySQL、PostgreSQL、SQL Server，DBeaver 会更适合。

它是一个通用数据库客户端，SQLite 只是其中一种连接类型。

官方网站：

```text
https://dbeaver.io/download/
```

选择 Community Edition，也就是社区版。Windows 上可以下载 Installer 安装包。

### 用 DBeaver 打开 SQLite

安装后启动 DBeaver：

1. 点击新建连接。
2. 选择 `SQLite`。
3. 选择本地数据库文件。
4. 第一次连接时，如果提示下载 SQLite 驱动，按提示下载。
5. 连接成功后，在左侧展开表。

DBeaver 的优势是功能强：

- 多数据库统一管理。
- SQL 编辑体验更完整。
- 查询结果导出选项更多。
- 适合经常写 SQL 的开发者。

但如果你只是偶尔看一个 `.db` 文件，DB Browser for SQLite 更轻一些。

## 5. 推荐工具四：VS Code 插件

如果你本来就在 VS Code 里看项目代码，也可以装 SQLite 插件。

常见插件名称包括：

- `SQLite Viewer`
- `SQLite`
- `SQLite3 Editor`

使用方式通常是：

1. 打开 VS Code。
2. 进入 Extensions。
3. 搜索 SQLite。
4. 选择评分较高、维护较新的插件安装。
5. 在资源管理器里右键 `.db` 文件，选择打开或查看数据库。

VS Code 插件适合“边看代码边看数据库”。例如你正在排查某个接口为什么没有返回数据，可以一边看后端代码，一边打开 SQLite 文件确认表里到底有没有那条记录。

不过插件体验会随插件维护情况变化。如果只是为了稳定查看数据，仍然建议装 DB Browser for SQLite。

## 6. 常见问题

### 问题一：打开数据库提示 file is not a database

这通常表示：

- 这个文件不是 SQLite 数据库。
- 文件损坏了。
- 你拿到的是压缩包、缓存文件、日志文件，但后缀刚好叫 `.db`。
- 应用使用了加密 SQLite，普通工具无法直接打开。

可以换 sqlite3 命令行试一下：

```powershell
sqlite3 D:\demo\database.db ".tables"
```

如果仍然报错，就要回到项目代码里确认数据库路径和格式。

### 问题二：数据库文件被占用，不能保存

如果应用正在运行，它可能正在读写这个 SQLite 文件。

建议：

- 先关闭正在运行的应用。
- 或者复制一份数据库文件，只查看副本。
- 不要在应用运行时用图形化工具随意修改原始数据库。

SQLite 支持多进程读写控制，但新手排查问题时，不要把“查看数据”和“应用正在写数据”混在一起。

### 问题三：看不到表，只有空数据库

常见原因有两个。

第一，你打开错文件了。很多项目会在不同环境生成不同数据库，例如：

```text
dev.db
test.db
prod.db
```

第二，应用实际使用的是另一个路径。尤其在 Windows 上，相对路径可能和你想的不一样。

例如代码里写：

```text
sqlite:///./database.db
```

这个 `./database.db` 是相对于程序启动目录，不一定是源码文件所在目录。

排查方法：

- 在项目里搜索数据库文件名。
- 看 `.env`、配置文件、启动脚本。
- 看应用启动日志里有没有数据库路径。
- 用 PowerShell 在项目目录递归查找 `.db` 文件。

### 问题四：中文显示乱码

SQLite 内部通常使用 UTF-8 存文本。乱码更多发生在导出 CSV 后用 Excel 打开时。

处理方式：

- 在 DB Browser for SQLite 里直接查看，通常不会乱码。
- 用 VS Code 打开 CSV，确认编码是 UTF-8。
- 在 Excel 里通过“数据”导入 CSV，而不是直接双击打开。

### 问题五：能不能直接双击 `.db` 文件打开

通常不行。Windows 不知道 `.db` 应该交给哪个程序处理。

正确做法是：

- 先打开 DB Browser for SQLite，再选择 `Open Database`。
- 或者在命令行里执行 `sqlite3 路径\文件名.db`。
- 或者在 DBeaver / VS Code 插件里创建连接。

## 7. 工具怎么选

可以按下面的方式选：

| 场景 | 推荐工具 |
| --- | --- |
| 第一次查看 SQLite，只想看表和数据 | DB Browser for SQLite |
| 想执行简单 SQL、查看表结构 | DB Browser for SQLite 或 sqlite3 |
| 经常排查后端问题、写脚本 | sqlite3 |
| 同时管理多种数据库 | DBeaver |
| 主要在 VS Code 里写代码 | VS Code SQLite 插件 |

我的建议是：

1. 先安装 DB Browser for SQLite，解决 80% 的查看需求。
2. 再下载 SQLite 官方命令行工具，学会 `.tables`、`.schema`、`SELECT`。
3. 如果你已经在用 DBeaver，就直接把 SQLite 也放到 DBeaver 里管理。

## 8. 一个最小排查流程

假设你拿到一个 AI 生成的小网页应用，里面有一个 `database.db`，想确认用户数据有没有写进去。

可以这样做：

1. 关闭正在运行的应用。
2. 复制 `database.db` 为 `database-copy.db`。
3. 用 DB Browser for SQLite 打开 `database-copy.db`。
4. 进入 `Database Structure`，确认有哪些表。
5. 进入 `Browse Data`，选择看起来像用户表的表，例如 `users`、`user`、`accounts`。
6. 如果表很多，切到 `Execute SQL` 执行：

```sql
SELECT name
FROM sqlite_master
WHERE type = 'table'
ORDER BY name;
```

7. 找到目标表后，再执行：

```sql
SELECT *
FROM users
ORDER BY id DESC
LIMIT 20;
```

如果能看到最新记录，说明数据确实写进数据库了。接下来再排查接口、页面展示或业务逻辑。

## 9. 总结

SQLite 的特点是简单：一个文件就是一个数据库。也正因为简单，很多本地应用、示例项目、AI 生成的小网页应用都会用它保存数据。

在 Windows 上查看 SQLite，最实用的组合是：

- DB Browser for SQLite：图形化查看、筛选、执行 SQL、导出数据。
- sqlite3 命令行：快速检查、脚本化查询、备份数据库。
- DBeaver 或 VS Code 插件：适合已经有固定开发工作流的人。

最重要的习惯只有一个：不要直接拿生产或正在运行的数据库文件练手，先复制一份再打开。

