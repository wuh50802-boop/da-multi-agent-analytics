-- ============================================================
-- 电商数据智能分析平台 · 建表脚本
-- 数据库：multi_agent_db
-- 命名规范：英文表名 + 中文字段名
-- 分层：ODS(原始快照) -> DWD(订单明细) -> DWS(达人日汇总) -> ADS(达人月榜)
-- 说明：仅新增表，不 DROP 任何现有对象；旧的 ods_posts 等表保留
-- ============================================================

CREATE DATABASE IF NOT EXISTS `multi_agent_db`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_unicode_ci;

USE `multi_agent_db`;

-- ------------------------------------------------------------
-- 1. ODS 层：原始订单快照
--    一单一行，保留数据源原始 JSON，不解析、不清洗
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ods_orders_raw` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `数据来源` VARCHAR(32) NOT NULL COMMENT '来源平台：抖店/微信/小红书',
  `源记录ID` VARCHAR(64) NOT NULL COMMENT '数据源中的原始订单ID',
  `原始数据` JSON NOT NULL COMMENT '未解析的原始订单JSON',
  `摄入时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '写入时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_source_record` (`数据来源`, `源记录ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ODS 原始订单快照表';

-- ------------------------------------------------------------
-- 2. DWD 层：订单明细宽表（核心 30 字段）
--    维度 18 + 度量 10 + 系统 2
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `dwd_orders` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',

  `订单ID` VARCHAR(64) NOT NULL COMMENT '主订单ID',
  `子订单ID` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '子订单ID，无则为空',
  `平台` VARCHAR(16) NOT NULL COMMENT '抖店/微信/小红书',
  `店铺ID` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '店铺ID',
  `用户ID` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '用户唯一标识',
  `商品ID` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '商品ID',
  `SKU` VARCHAR(64) NOT NULL DEFAULT '' COMMENT 'SKU ID',
  `商品名称` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '商品名称',
  `达人UID` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '达人ID，小店自卖记为0',
  `达人名称` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '达人昵称',
  `订单状态` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '订单状态',
  `售后状态` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '售后状态，无则为空',
  `支付方式` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '支付方式',
  `提交时间` DATETIME DEFAULT NULL COMMENT '订单提交时间',
  `支付时间` DATETIME DEFAULT NULL COMMENT '订单支付时间',
  `收件省份` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '收件人省份',
  `收件城市` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '收件人城市',
  `数据来源` VARCHAR(32) NOT NULL DEFAULT '' COMMENT '数据来源系统',

  `购买数量` DECIMAL(18,0) NOT NULL DEFAULT 0 COMMENT '商品数量',
  `订单总额` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '订单总金额(GMV，元)',
  `商家实收` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '商家实收金额(元)',
  `买家实付` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '买家实付金额(元)',
  `退款金额` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '退款金额(元)',
  `结算金额` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '结算金额(元)',
  `达人佣金` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '达人佣金(元)',
  `平台佣金` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '平台佣金(元)',
  `运费` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '运费(元)',
  `优惠金额` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '优惠总金额(元)',

  `创建时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `更新时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',

  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_order` (`订单ID`, `平台`, `子订单ID`),
  KEY `idx_platform_time` (`平台`, `提交时间`),
  KEY `idx_kol` (`达人UID`),
  KEY `idx_submit_time` (`提交时间`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWD 电商订单明细宽表';

-- ------------------------------------------------------------
-- 3. DWS 层：达人 x 日期 x 平台 日汇总
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `dws_kol_daily` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `统计日期` DATE NOT NULL COMMENT '统计日期',
  `平台` VARCHAR(16) NOT NULL COMMENT '抖店/微信/小红书',
  `达人UID` VARCHAR(64) NOT NULL COMMENT '达人ID',
  `达人名称` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '达人昵称',
  `支付订单数` INT NOT NULL DEFAULT 0 COMMENT '支付成功订单数',
  `销量` DECIMAL(18,0) NOT NULL DEFAULT 0 COMMENT '商品销量',
  `GMV` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '订单总额(元)',
  `实付金额` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '买家实付金额(元)',
  `退款金额` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '退款金额(元)',
  `净GMV` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT 'GMV减退款(元)',
  `达人佣金` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '达人佣金(元)',
  `创建时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `更新时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kol_day` (`统计日期`, `平台`, `达人UID`),
  KEY `idx_date` (`统计日期`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DWS 达人日汇总表';

-- ------------------------------------------------------------
-- 4. ADS 层：达人月度榜单
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ads_kol_rank` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `统计月份` CHAR(7) NOT NULL COMMENT '统计月份，格式 YYYY-MM',
  `平台` VARCHAR(16) NOT NULL COMMENT '抖店/微信/小红书',
  `达人UID` VARCHAR(64) NOT NULL COMMENT '达人ID',
  `达人名称` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '达人昵称',
  `月度GMV` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '当月GMV(元)',
  `支付订单数` INT NOT NULL DEFAULT 0 COMMENT '当月支付订单数',
  `退货率` DECIMAL(8,4) NOT NULL DEFAULT 0.0000 COMMENT '退款订单占比',
  `排名` INT NOT NULL DEFAULT 0 COMMENT '当月GMV排名',
  `创建时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `更新时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kol_month` (`统计月份`, `平台`, `达人UID`),
  KEY `idx_rank` (`统计月份`, `平台`, `排名`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='ADS 达人月度榜单表';

-- ------------------------------------------------------------
-- 5. DIM 层：商品维表（平台 x 商品ID）
--    从 DWD 聚合出商品的累计表现，供"某商品卖得怎么样"类问题直查
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `dim_product` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `平台` VARCHAR(16) NOT NULL COMMENT '抖店/微信/小红书',
  `商品ID` VARCHAR(64) NOT NULL COMMENT '商品ID',
  `商品名称` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '商品名称（取最新）',
  `总销量` DECIMAL(18,0) NOT NULL DEFAULT 0 COMMENT '累计支付销量',
  `总GMV` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '累计订单总额(元)',
  `总实付金额` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '累计买家实付(元)',
  `总退款金额` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '累计退款(元)',
  `最早成交时间` DATETIME DEFAULT NULL COMMENT '最早支付时间',
  `最后成交时间` DATETIME DEFAULT NULL COMMENT '最后支付时间',
  `创建时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `更新时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_platform_product` (`平台`, `商品ID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DIM 商品维度表';

-- ------------------------------------------------------------
-- 6. DIM 层：达人维表（平台 x 达人UID）
--    从 DWD 聚合出达人的累计表现，供"某达人带货能力"类问题直查
-- ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `dim_kol` (
  `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '自增主键',
  `平台` VARCHAR(16) NOT NULL COMMENT '抖店/微信/小红书',
  `达人UID` VARCHAR(64) NOT NULL COMMENT '达人ID',
  `达人名称` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '达人名称（取最新）',
  `支付订单数` INT NOT NULL DEFAULT 0 COMMENT '累计支付订单数',
  `总销量` DECIMAL(18,0) NOT NULL DEFAULT 0 COMMENT '累计销量',
  `总GMV` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '累计订单总额(元)',
  `净GMV` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '累计GMV减退款(元)',
  `总佣金` DECIMAL(18,2) NOT NULL DEFAULT 0.00 COMMENT '累计达人佣金(元)',
  `退货率` DECIMAL(8,4) NOT NULL DEFAULT 0.0000 COMMENT '退款订单占比',
  `最早成交时间` DATETIME DEFAULT NULL COMMENT '最早支付时间',
  `最后成交时间` DATETIME DEFAULT NULL COMMENT '最后支付时间',
  `创建时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  `更新时间` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '记录更新时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_platform_kol` (`平台`, `达人UID`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='DIM 达人维度表';
