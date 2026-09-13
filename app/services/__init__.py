"""
服务层（service layer）

承接路由的"业务动作"，让 router 只做参数绑定：
    依赖注入 → 调用本层 → 返回响应。

依赖方向（硬约束）：
    app.api.routers → app.services → app.utils / app.repositories / app.core
本层**不得** import `app.api.*`，否则会形成 api → services → api 的环。
也不直接持有管线对象——graph 仍由路由通过 `Depends` 注入后转传。
"""
