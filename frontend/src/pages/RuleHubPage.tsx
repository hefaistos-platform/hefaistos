import React from 'react';
import { Tabs } from 'antd';
import { RuleSearchPage } from './RuleSearchPage';
import { RuleStatisticsPanel } from '../sections/RuleStatisticsPanel';

export const RuleHubPage: React.FC = () => {
  const [activeTab, setActiveTab] = React.useState('search');
  const [searchVersion, setSearchVersion] = React.useState(0);
  const openSearch = () => {
    setSearchVersion(version => version + 1);
    setActiveTab('search');
  };
  return (
    <div style={{ padding: 24 }}>
      <Tabs
        activeKey={activeTab}
        onChange={setActiveTab}
        items={[
          {
            key: 'search',
            label: 'Rule Search',
            children: <RuleSearchPage key={searchVersion} />,
          },
          {
            key: 'stats',
            label: 'Rule Statistics',
            children: <RuleStatisticsPanel onSearch={openSearch} />,
          },
        ]}
      />
    </div>
  );
};
