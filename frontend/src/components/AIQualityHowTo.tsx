import React from 'react';
import { Collapse, Typography } from 'antd';

export function RuleFeedbackHowTo() {
  return <>
    <Typography.Paragraph>Help improve the next AI-generated rule by explaining a correction you made.</Typography.Paragraph>
    <ol style={{ paddingLeft: 24 }}>
      <li>Generate a rule with <strong>Generate with AI</strong>, or generate a rule from MVE.</li>
      <li>Correct the rule in the editor, then save it. In the Workbench editor, use the format save button
        (for example, <strong>SAVE KQL</strong>) or <strong>SAVE ALL</strong>. In the Rule Hub editor, use its save button;
        when editing raw rule content on the detail page, click <strong>Save</strong>.</li>
      <li>Open <strong>AI feedback</strong> beside the save controls, or on the saved rule's detail page. Select <strong>Explain correction</strong> for the saved change.</li>
      <li>Choose what changed, explain what was wrong and how you fixed it, and describe how you checked the correction. Click <strong>Submit feedback</strong>.</li>
    </ol>
    <Typography.Paragraph>Example: choose <strong>Incorrect table</strong>, explain that the generated rule used DeviceProcessEvents,
      and describe replacing it with ProcessEvents_CL to match your telemetry.</Typography.Paragraph>
    <Typography.Paragraph>If the edit simply reflects new requirements or a preference, choose <strong>Intentional edit / dismiss</strong> instead.</Typography.Paragraph>
    <Typography.Paragraph type="secondary">Your admin reviews the feedback in Configuration → AI Quality. Submitting feedback does not change active prompts.</Typography.Paragraph>
  </>;
}

export default function AIQualityHowTo() {
  return <Collapse style={{ marginBottom: 16 }} items={[{
    key: 'how-to', label: 'How to use AI Quality', children: <>
      <Typography.Title level={5}>For rule authors: send feedback</Typography.Title>
      <RuleFeedbackHowTo />
      <Typography.Title level={5}>For admins: review and improve</Typography.Title>
      <ol style={{ paddingLeft: 24 }}>
        <li>In <strong>Correction feedback</strong>, select the organization and rule language, then review submitted corrections.</li>
        <li>Inspect the diff and explanation. Choose <strong>Review and accept</strong>, classify the likely root cause, and record your review reason. Choose PROMPT only when the instructions caused the problem.</li>
        <li>In <strong>Improvement proposals</strong>, choose <strong>New improvement proposal</strong>. Select accepted prompt-related corrections and add regression cases where possible.</li>
        <li>Write instructions or request an AI suggestion. Specify what each case must verify, then choose <strong>Save proposal</strong>.</li>
        <li>Choose <strong>Evaluate</strong>, then <strong>Assess outputs</strong>. Compare baseline and proposed rules and record a decision with evidence for every case.</li>
        <li>When checks and assessments pass, choose <strong>Review and activate</strong>, inspect the exact instructions, and approve with a reason.</li>
      </ol>
      <Typography.Paragraph type="secondary">Evaluation makes two model calls per case and requires configured AI credentials and a running worker.
        Table mappings, missing context, retrieval, and application problems may need fixes outside the prompts.</Typography.Paragraph>
    </>,
  }]} />;
}
