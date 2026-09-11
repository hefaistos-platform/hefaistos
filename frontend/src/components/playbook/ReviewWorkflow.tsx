import React, { useState } from 'react';
import { message, notification, Button as AntButton } from 'antd';
import { gql } from '@apollo/client';
import { useMutation } from '@apollo/client/react';
import { Button } from '../ui/Button';
import { PixelIcon } from '../ui/PixelIcon';
import { useNavigate } from 'react-router-dom';

// --- QUERIES/MUTATIONS ---
const SUBMIT_MUTATION = gql`
    mutation Submit($graphId: UUID!, $note: String) {
        submitForReview(graphId: $graphId, note: $note) {
            success
            reviewRequest {
                id
                status
                createdAt
                author { username }
                comments { id text createdAt user { username } }
            }
        }
    }
`;

const FINALIZE_MUTATION = gql`
  mutation Finalize($reqId: UUID!, $decision: String!, $feedback: String!) {
    finalizeReview(requestId: $reqId, decision: $decision, feedback: $feedback) {
      success
    }
  }
`;

const ADMIN_DEPLOY_MUTATION = gql`
    mutation AdminDeploy($id: UUID!) {
        adminApproveDeployment(id: $id) {
            playbookGraph { id status }
        }
    }
`;

type ReviewComment = { id: string; text: string; createdAt: string; user?: { username?: string } };
type SubmitForReviewData = { submitForReview: { success: boolean; reviewRequest?: { id: string; status: string; createdAt: string; author?: { username?: string }; comments: ReviewComment[] } } };
type FinalizeReviewData = { finalizeReview: { success: boolean } };
type AdminApproveDeploymentData = { adminApproveDeployment: { playbookGraph: { id: string; status: string } } };

export const ReviewWorkflow: React.FC<any> = ({ playbookId, status, activeReview, userRole, isAuthor = false, refetch }) => {
    const [submitReview, { loading: creatingReview }] = useMutation<SubmitForReviewData>(SUBMIT_MUTATION);
    const [finalizeReview, { loading: finalizingReview }] = useMutation<FinalizeReviewData>(FINALIZE_MUTATION);
    const [adminDeploy, { loading: deploying }] = useMutation<AdminApproveDeploymentData>(ADMIN_DEPLOY_MUTATION);
    const navigate = useNavigate();
  
  const [comment, setComment] = useState("");

    const handleSubmit = async () => {
            console.log('[ReviewWorkflow] handleSubmit called with playbookId:', playbookId, 'note:', comment);
            try {
                const res = await submitReview({ variables: { graphId: playbookId, note: comment } });
                console.log('[ReviewWorkflow] submitReview response:', res);
                const payload = res?.data?.submitForReview;
                if (payload?.success) {
                    message.success('Review requested. Moved to Peer Review.');
                    console.log('[ReviewWorkflow] Submit succeeded, reviewRequest:', payload.reviewRequest);
                } else {
                    message.warning('Submit returned without success.');
                    console.warn('[ReviewWorkflow] Submit returned without success:', payload);
                }
            } catch (e: any) {
                console.error('Submit review error:', e);
                message.error(e?.message || 'Failed to submit review request.');
            }
            setComment("");
            // Always refetch to pull latest status and active review
            console.log('[ReviewWorkflow] Calling refetch...');
            await refetch();
            console.log('[ReviewWorkflow] refetch completed');
    };

    const handleDecision = async (decision: "APPROVE" | "REJECT") => {
            if (!comment) return alert("Please provide formal feedback.");
            if (!activeReview?.id) {
                message.error('No active review to finalize.');
                return;
            }
            try {
                const res = await finalizeReview({ variables: { reqId: activeReview.id, decision, feedback: comment } });
                if (res?.data?.finalizeReview?.success) {
                    message.success(decision === 'APPROVE' ? 'Approved. Status moved to Approved.' : 'Rejected. Status moved to In Research.');
                } else {
                    message.warning('Finalize returned without success.');
                }
            } catch (e: any) {
                console.error('Finalize review error:', e);
                message.error(e?.message || 'Failed to finalize review.');
            }
            setComment("");
            // Always refetch to pull latest status
            await refetch();
    };

    const handleAdminDeploy = async () => {
            try {
                const res = await adminDeploy({ variables: { id: playbookId } });
                const nextStatus = res?.data?.adminApproveDeployment?.playbookGraph?.status;
                                if (nextStatus === 'DEPLOYED') {
                    message.success('Deployment approved. Status moved to Deployed.');
                                        // Hint user that coverage has been updated and provide a quick link to Coverage Map
                                        notification.open({
                                            message: 'Coverage updated',
                                            description: 'Open Coverage Map and click Refresh to view the latest coverage.',
                                            btn: (
                                                <AntButton type="primary" size="small" onClick={() => { navigate('/coverage'); notification.destroy(); }}>
                                                    Open Coverage Map
                                                </AntButton>
                                            ),
                                            placement: 'bottomRight',
                                            duration: 6
                                        });
                } else {
                    message.info('Deployment action completed.');
                }
            } catch (e: any) {
                console.error('Admin deploy error:', e);
                message.error(e?.message || 'Failed to approve deployment. Ensure status is Approved and you are Admin.');
            }
            await refetch();
    };

        const roleCode = (userRole || '').toString().toUpperCase();
        const isReviewer = roleCode === 'ADMIN' || roleCode === 'REVIEWER';
        const isOpenReview = !!activeReview && (activeReview.status || '').toString().toUpperCase() === 'OPEN' && (status || '').toString().toUpperCase() === 'REVIEW';

  return (
    <div className="p-6 bg-white border-2 border-hefaistos-border rounded-lg shadow-sm mt-6">
       <h2 className="text-xl font-bold mb-4 text-hefaistos-primary flex items-center">
         <PixelIcon name="check-circle" className="w-6 h-6 mr-2" />
         Part 6: Review Workflow
      </h2>

      {/* CASE A: Draft/No Open Review → Submit */}
      {!isOpenReview && status !== 'DEPLOYED' && (
          <div className="bg-gray-50 p-4 rounded border text-center">
              <p className="text-sm text-gray-600 mb-3">Playbook is currently in <strong>{status}</strong>.</p>
              <textarea 
                  className="w-full p-2 border rounded text-sm mb-2" 
                  placeholder="Notes for the reviewer..." 
                  value={comment} onChange={e => setComment(e.target.value)}
              />
              <Button type="button" variant="primary" onClick={handleSubmit} disabled={!isAuthor || creatingReview}>
                  {creatingReview ? 'Submitting…' : 'Submit Request'}
              </Button>
              {!isAuthor && <p className="text-xs text-gray-400 mt-2">Only the author can submit for review.</p>}
          </div>
      )}

      {/* CASE B: Active Review (Open + status REVIEW) */}
      {isOpenReview && (
          <div className="bg-blue-50 p-4 rounded border border-blue-200">
              <div className="flex justify-between items-start mb-4">
                  <div>
                      <h3 className="font-bold text-blue-800">Review In Progress</h3>
                      <p className="text-xs text-blue-600">
                          Requested on {new Date(activeReview.createdAt).toLocaleDateString()}
                      </p>
                  </div>
                  <span className="bg-yellow-100 text-yellow-800 text-xs px-2 py-1 rounded font-bold">PENDING</span>
              </div>

              {/* Thread History */}
              <div className="space-y-3 mb-4 max-h-40 overflow-y-auto bg-white p-3 rounded border">
                  {(activeReview.comments || []).length === 0 && (
                      <p className="text-sm text-gray-400 italic">No comments yet.</p>
                  )}
                  {(activeReview.comments || []).map((c: any) => (
                      <div key={c.id} className="text-sm">
                          <span className="font-bold text-gray-700">{c.user?.username || 'Unknown'}:</span> {c.text}
                      </div>
                  ))}
              </div>

              {/* Reviewer Actions */}
                            {isReviewer ? (
                  <div>
                      <textarea 
                          className="w-full p-2 border rounded text-sm mb-2" 
                          placeholder="Formal feedback (Required for decision)..." 
                          value={comment} onChange={e => setComment(e.target.value)}
                      />
                      <div className="flex gap-2 justify-end">
                                                    <Button type="button" variant="danger" onClick={() => handleDecision('REJECT')} disabled={finalizingReview}>Reject</Button>
                                                    <Button type="button" variant="primary" onClick={() => handleDecision('APPROVE')} disabled={finalizingReview}>Approve</Button>
                      </div>
                  </div>
              ) : (
                  <p className="text-sm text-gray-500 italic text-center">Waiting for a reviewer to take action.</p>
              )}
          </div>
      )}

            {/* CASE C: Deployed */}
      {status === 'DEPLOYED' && (
          <div className="bg-green-50 p-4 rounded border border-green-200 text-center">
              <h3 className="font-bold text-green-800">Playbook Deployed</h3>
              <p className="text-sm text-green-600">This logic is active in production.</p>
          </div>
      )}

            {/* Admin-only Deploy action when Approved */}
            {status === 'APPROVED' && (userRole || '').toUpperCase() === 'ADMIN' && (
                <div className="bg-purple-50 p-4 rounded border border-purple-200 text-center mt-4">
                    <p className="text-sm text-purple-700 mb-2">Admin can approve deployment for this Approved workbench.</p>
                    <Button type="button" variant="primary" onClick={handleAdminDeploy} disabled={deploying}>
                        {deploying ? 'Deploying…' : 'Approve Deployment'}
                    </Button>
                </div>
            )}
    </div>
  );
};
