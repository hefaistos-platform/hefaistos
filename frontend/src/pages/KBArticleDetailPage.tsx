import React from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { gql } from '@apollo/client';
import { useQuery } from '@apollo/client/react';
import { Button, Card, Typography, Space, Breadcrumb, Tag } from 'antd';
import { PixelIcon } from '../components/ui/PixelIcon';
import { MarkdownRenderer } from '../components/MarkdownRenderer';

// --- GraphQL Query ---
const GET_KB_ARTICLE_QUERY = gql`
	query GetKBArticle($id: UUID!) {
		me {
			role
		}
		kbArticle(id: $id) {
			id
			title
			content
			updatedAt
			author {
				username
			}
			category {
				id
				name
			}
		}
	}
`;

// --- TypeScript Types ---
interface KBArticleDetails {
	id: string;
	title: string;
	content: string;
	updatedAt: string;
	author: { username: string } | null;
	category: { id: string; name: string } | null;
}
interface GetArticleData {
	kbArticle: KBArticleDetails | null;
	me?: { role: string } | null;
}

export const KBArticleDetailPage: React.FC = () => {
	const { articleId } = useParams<{ articleId: string }>();
	const navigate = useNavigate();

	const { data, loading, error } = useQuery<GetArticleData>(GET_KB_ARTICLE_QUERY, {
		variables: { id: articleId },
	});

	if (loading) return <p>Loading article...</p>;
	if (error) return <p className="text-hefaistos-accent-red">Error: {error.message}</p>;
	if (!data || !data.kbArticle) return <p>Article not found.</p>;

	const { kbArticle: article } = data;
	const isElOne = (data?.me?.role || '').toUpperCase() === 'ELONE';

	const handleEdit = () => {
		navigate(`/kb/edit/${article!.id}`); // Will be implemented later
	};

	return (
		<div className="max-w-4xl mx-auto">
			<Breadcrumb style={{ marginBottom: 12 }}>
				<Breadcrumb.Item><Link to="/kb">Knowledge Base</Link></Breadcrumb.Item>
				{article!.category?.name && <Breadcrumb.Item>{article!.category!.name}</Breadcrumb.Item>}
				<Breadcrumb.Item>{article!.title}</Breadcrumb.Item>
			</Breadcrumb>
			<Card
				title={<Typography.Title level={2} style={{ margin: 0 }}>{article!.title}</Typography.Title>}
				extra={
					<Space>
						<Button onClick={() => navigate('/kb')}>
							<PixelIcon name="back" className="w-5 h-5" />
							<span style={{ marginLeft: 8 }}>Back</span>
						</Button>
						{!isElOne && (
							<Button type="primary" onClick={handleEdit}>
								<PixelIcon name="edit" className="w-5 h-5" />
								<span style={{ marginLeft: 8 }}>Edit</span>
							</Button>
						)}
					</Space>
				}
			>
				<Space size={16} style={{ marginBottom: 16 }} wrap>
					<Typography.Text type="secondary">By {article!.author?.username || 'N/A'}</Typography.Text>
					<Typography.Text type="secondary">Updated {new Date(article!.updatedAt).toLocaleDateString()}</Typography.Text>
					{article!.category && <Tag>{article!.category!.name}</Tag>}
				</Space>
				<MarkdownRenderer content={article!.content} variant="default" />
			</Card>
		</div>
	);
};

export default KBArticleDetailPage;
