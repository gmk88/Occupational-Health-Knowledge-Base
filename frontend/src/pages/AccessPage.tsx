import { Card, CardGrid, PageHeader } from '../components/ui';
import { AccessClients } from '../features/access/AccessClients';
import { AccountManager } from '../features/access/AccountManager';
import { UsagePanel } from '../features/access/UsagePanel';

export function AccessPage() {
  return (
    <main className="page access-page">
      <PageHeader
        eyebrow="ACCESS / 06"
        title="接入管理"
        description="给外部模型的 MCP 客户端分配密钥与限额，管理登录账号，并查看每一方的调用用量。"
        meta="密钥只在创建时显示一次"
      />

      <CardGrid>
        <Card
          span={12}
          eyebrow="ACCESS / 01"
          title="用量统计"
          description="曲线展示调用趋势，点击下方任一行可只看该接入方。"
        >
          <UsagePanel />
        </Card>

        <Card
          span={12}
          eyebrow="ACCESS / 02"
          title="接入方与密钥"
          description="每个接入方一个独立密钥；轮换后旧密钥立即失效。"
        >
          <AccessClients />
        </Card>

        <Card
          span={12}
          eyebrow="ACCESS / 03"
          title="账号管理"
          description="为同事创建只读或管理员账号；停用后会话立即失效。"
        >
          <AccountManager />
        </Card>
      </CardGrid>
    </main>
  );
}
