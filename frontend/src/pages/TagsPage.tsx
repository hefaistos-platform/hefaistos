import React from 'react';
import { Card, Typography } from 'antd';

export const TagsPage: React.FC = () => {
  return (
    <Card>
      <Typography.Title level={3}>Tags</Typography.Title>
      <Typography.Paragraph>
        Placeholder for tag administration. Future features: bulk rename, merge tags, usage analytics.
      </Typography.Paragraph>
    </Card>
  );
};
