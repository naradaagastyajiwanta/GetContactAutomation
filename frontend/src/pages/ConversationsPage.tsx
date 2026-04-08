import { useState } from "react";
import { MessageSquare } from "lucide-react";
import { useConversations } from "../hooks/useConversations";
import { ConversationFilters } from "../components/conversations/ConversationFilters";
import { ConversationList } from "../components/conversations/ConversationList";
import { Pagination } from "../components/ui/Pagination";
import { Spinner } from "../components/ui/Spinner";
import { EmptyState } from "../components/ui/EmptyState";
import { ITEMS_PER_PAGE } from "../lib/constants";
import { usePageTour } from "../hooks/usePageTour";
import { CONVERSATIONS_TOUR_STEPS } from "../tours/conversations.tour";

export default function ConversationsPage() {
  const [state, setState] = useState("");
  const [page, setPage] = useState(1);

  const offset = (page - 1) * ITEMS_PER_PAGE;
  const { data: conversations, isLoading } = useConversations({
    state: state || undefined,
    limit: ITEMS_PER_PAGE,
    offset,
  });

  usePageTour("conversations", CONVERSATIONS_TOUR_STEPS);

  const handleStateChange = (newState: string) => {
    setState(newState);
    setPage(1);
  };

  const totalPages = conversations
    ? Math.max(
        1,
        Math.ceil(conversations.length / ITEMS_PER_PAGE) +
          (conversations.length === ITEMS_PER_PAGE ? 1 : 0),
      )
    : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Conversations
        </h1>
        <div data-tour="conversations-filters">
          <ConversationFilters
            state={state}
            onStateChange={handleStateChange}
          />
        </div>
      </div>

      {isLoading ? (
        <div className="flex justify-center py-12">
          <Spinner size="lg" />
        </div>
      ) : !conversations || conversations.length === 0 ? (
        <EmptyState
          icon={MessageSquare}
          title="No conversations"
          description="No conversations match the current filter. Try changing the state filter."
        />
      ) : (
        <>
          <div data-tour="conversations-list">
            <ConversationList conversations={conversations} />
          </div>
          <div className="flex justify-center">
            <Pagination
              currentPage={page}
              totalPages={totalPages}
              onPageChange={setPage}
            />
          </div>
        </>
      )}
    </div>
  );
}
