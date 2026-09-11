import React from 'react';
import { gql } from '@apollo/client';
import { useQuery, useMutation } from '@apollo/client/react';
import CreatableSelect from 'react-select/creatable';

// Query to get all tags for the organization
const GET_ALL_TAGS_QUERY = gql`
  query GetAllTags {
    allTags {
      name
    }
  }
`;

// Mutation to update the tags on a playbook
const UPDATE_PLAYBOOK_TAGS_MUTATION = gql`
  mutation UpdatePlaybookTags($playbookId: UUID!, $tagNames: [String!]!) { # FIX: Changed type to [String!]!
    updatePlaybookTags(playbookId: $playbookId, tagNames: $tagNames) {
      playbook {
        id
        tags {
          id
          name
        }
      }
    }
  }
`;

interface Tag {
  id: string; // Added ID, as it is used in the mutation response
  name: string;
}

interface TagOption {
  value: string;
  label: string;
}

interface TagManagerProps {
  playbookId: string;
  currentTags: Tag[]; // FIX: Changed type to Tag[]
}

export const TagManager: React.FC<TagManagerProps> = ({ playbookId, currentTags }) => {
  // Fetch all tags for the organization to populate the dropdown
  const { data: allTagsData, loading: tagsLoading } = useQuery<{ allTags: Tag[] }>(GET_ALL_TAGS_QUERY); // Added type for data

  // FIX: Correctly destructure useMutation to get the function and loading/error status
  const [updatePlaybookTags, { loading: updateLoading }] = useMutation(UPDATE_PLAYBOOK_TAGS_MUTATION);

  const handleTagChange = (selectedOptions: readonly TagOption[]) => { // Added [] for selectedOptions
    const tagNames = selectedOptions.map(option => option.value);
    updatePlaybookTags({
      variables: {
        playbookId,
        tagNames,
      },
    });
  };

  // FIX: Correctly type tagOptions as an array and add default empty array
  const tagOptions: TagOption[] = allTagsData?.allTags.map((tag: Tag) => ({
    value: tag.name,
    label: tag.name,
  })) || [];

  // FIX: Correctly type currentTagValues as an array
  const currentTagValues: TagOption[] = currentTags.map(tag => ({
    value: tag.name,
    label: tag.name,
  }));

  return (
    // FIX: Wrapped in parentheses for clean return
    <CreatableSelect
      isMulti
      isLoading={tagsLoading || updateLoading}
      onChange={handleTagChange}
      options={tagOptions}
      value={currentTagValues}
      placeholder="Add or create tags..."
    />
  );
};
