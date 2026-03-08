# Phase 2 Feature: K9 → Claude Code 错误广播

## 想法来源
2026-03-08 开发 K9Audit 时讨论

## 核心价值
当 AI coding agent 执行失败时，K9 不只是记录，
而是主动把因果根因广播给 agent，让它直接跳回去修根源。

## 为什么有价值
- Claude Code 太聪明，出错少，价值一般
- 便宜的 agent（GPT-4o mini、本地模型）出错频率高10倍
- 这些用户最需要这个功能，付费意愿也更强

## 技术实现（已想清楚）
hook_post.py 在检测到执行失败时：
  1. 调 CausalChainAnalyzer 找根因（已实现）
  2. 把根因写入 stderr
  3. Claude Code / 其他 agent 读到 stderr，直接定位修复

关键：不是单步错误广播（agent 自己能看到），
而是跨步骤隐藏污染的根因广播：
  Step#1 Write(report.py) 成功 → agent 不知道有问题
  Step#3 Bash 崩溃 → K9 广播 "根因在 Step#1，缺 import logging"
  → agent 直接跳回 Step#1 修，不在 Step#3 附近兜圈子

## 实现入口
k9log/hook_post.py — _send_causal_followup 已有基础
改成在执行失败时写 stderr 而不只是发告警

## 定价建议
- 免费版：记录 + k9log causal --last（用户手动查）
- 付费版：自动广播根因给 agent（agent 自动修）

## 目标用户
使用便宜但不够聪明的 agent 的开发者
尤其是：本地模型用户、API 成本敏感用户

记录时间：2026-03-08 16:19