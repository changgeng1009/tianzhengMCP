# Visual Review Prompt

只依据局部 crop、overlay、PDF region 和 CAD anchors 判断对象类型与位置。证据不足保持 review_only；不得从页面尺寸推导 CAD 坐标，不得为了执行而确认不确定 TDb 对象。输出 evidence IDs、confidence、reason 和 required follow-up。
