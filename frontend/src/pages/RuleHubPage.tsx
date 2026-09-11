import React from 'react';
import { Tabs } from 'antd';
import { RuleSearchPage } from './RuleSearchPage';
import { RuleStatisticsPanel } from '../sections/RuleStatisticsPanel';

export const RuleHubPage: React.FC = () => {
  return (
    <div style={{ padding: 24 }}>
      <Tabs
        defaultActiveKey="search"
        items={[
          {
            key: 'search',
            label: 'Rule Search',
            children: <RuleSearchPage />,
          },
          {
            key: 'stats',
            label: 'Rule Statistics',
            children: <RuleStatisticsPanel />,
          },
        ]}
      />
    </div>
  );
};
