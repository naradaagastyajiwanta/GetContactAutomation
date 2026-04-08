import { Lightbulb, FileSearch, RefreshCw, Target } from "lucide-react";
import {
  useLessons,
  useAnalyses,
  useLearningStats,
  useTriggerReflection,
} from "../hooks/useLearning";
import { Spinner } from "../components/ui/Spinner";
import { Card } from "../components/ui/Card";
import { Badge } from "../components/ui/Badge";
import { Button } from "../components/ui/Button";
import { EmptyState } from "../components/ui/EmptyState";
import { useAuth } from "../context/AuthContext";
import { usePageTour } from "../hooks/usePageTour";
import { LEARNING_TOUR_STEPS } from "../tours/learning.tour";

const situationColors: Record<string, string> = {
  initial_contact:
    "bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200",
  follow_up:
    "bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-200",
  objection_handling:
    "bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-200",
  closing: "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  re_engagement:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
};

const outcomeColors: Record<string, string> = {
  GOT_NUMBER:
    "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-200",
  REFUSED: "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-200",
  ABANDONED:
    "bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-200",
  NO_REPLY: "bg-gray-100 text-gray-800 dark:bg-gray-700 dark:text-gray-200",
};

export default function LearningPage() {
  const { hasPermission } = useAuth();
  const { data: stats, isLoading: statsLoading } = useLearningStats();
  const { data: lessonsData, isLoading: lessonsLoading } = useLessons();
  const { data: analysesData, isLoading: analysesLoading } = useAnalyses(10);
  const triggerReflection = useTriggerReflection();
  const canManageLearning = hasPermission("learning.manage");
  usePageTour("learning", LEARNING_TOUR_STEPS);

  if (statsLoading || lessonsLoading || analysesLoading) {
    return (
      <div className="flex h-64 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  const lessons = lessonsData?.lessons ?? [];
  const analyses = analysesData?.analyses ?? [];
  const sortedLessons = [...lessons].sort(
    (a, b) => b.confidence - a.confidence,
  );

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Learning System
        </h1>
        {canManageLearning && (
          <Button
            onClick={() => triggerReflection.mutate()}
            loading={triggerReflection.isPending}
            size="sm"
          >
            <RefreshCw className="h-4 w-4" />
            Trigger Reflection
          </Button>
        )}
      </div>

      {/* Stats Row */}
      {stats && (
        <div data-tour="learning-stats" className="grid gap-4 sm:grid-cols-3">
          <Card>
            <div className="flex items-center gap-3">
              <Lightbulb className="h-8 w-8 text-amber-500" />
              <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {stats.total_active_lessons}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Total Active Lessons
                </p>
              </div>
            </div>
          </Card>
          <Card>
            <div className="flex items-center gap-3">
              <FileSearch className="h-8 w-8 text-indigo-500" />
              <div>
                <p className="text-2xl font-bold text-gray-900 dark:text-gray-100">
                  {stats.unprocessed_analyses}
                </p>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Unprocessed Analyses
                </p>
              </div>
            </div>
          </Card>
          <Card>
            <div className="flex items-center gap-3">
              <Target className="h-8 w-8 text-emerald-500" />
              <div>
                <p className="text-sm font-medium text-gray-500 dark:text-gray-400 mb-1">
                  Lessons by Situation
                </p>
                <div className="flex flex-wrap gap-1">
                  {Object.entries(stats.lessons_by_situation).map(
                    ([type, count]) => (
                      <Badge key={type} variant={situationColors[type]}>
                        {type.replace(/_/g, " ")}: {count}
                      </Badge>
                    ),
                  )}
                  {Object.keys(stats.lessons_by_situation).length === 0 && (
                    <span className="text-xs text-gray-400 dark:text-gray-500">
                      None yet
                    </span>
                  )}
                </div>
              </div>
            </div>
          </Card>
        </div>
      )}

      {/* Lessons Section */}
      <div data-tour="learning-lessons">
        <Card>
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
            Learned Lessons
          </h2>
          {sortedLessons.length === 0 ? (
            <EmptyState
              icon={Lightbulb}
              title="Belum ada pelajaran"
              description="Sistem akan belajar dari percakapan yang selesai."
            />
          ) : (
            <div className="space-y-4">
              {sortedLessons.map((lesson) => (
                <div
                  key={lesson.id}
                  className="rounded-lg border border-gray-100 p-4 dark:border-gray-700"
                >
                  <div className="mb-2 flex flex-wrap items-center gap-2">
                    <Badge variant={situationColors[lesson.situation_type]}>
                      {lesson.situation_type.replace(/_/g, " ")}
                    </Badge>
                    {lesson.province && <Badge>{lesson.province}</Badge>}
                    <span className="ml-auto text-sm text-gray-500 dark:text-gray-400">
                      {Math.round(lesson.success_rate * 100)}% success
                    </span>
                  </div>
                  <p className="mb-1 text-sm text-gray-900 dark:text-gray-100">
                    {lesson.insight}
                  </p>
                  <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                    {lesson.recommended_strategy}
                  </p>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      Confidence
                    </span>
                    <div className="h-2 flex-1 rounded-full bg-gray-200 dark:bg-gray-700">
                      <div
                        className="h-2 rounded-full bg-indigo-500"
                        style={{
                          width: `${Math.round(lesson.confidence * 100)}%`,
                        }}
                      />
                    </div>
                    <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                      {Math.round(lesson.confidence * 100)}%
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>

      {/* Recent Analyses Section */}
      <div data-tour="learning-analyses">
        <Card>
          <h2 className="mb-4 text-lg font-semibold text-gray-900 dark:text-gray-100">
            Recent Analyses
          </h2>
          {analyses.length === 0 ? (
            <EmptyState
              icon={FileSearch}
              title="Belum ada analisis"
              description="Analisis akan muncul setelah percakapan selesai."
            />
          ) : (
            <div className="space-y-3">
              {analyses.map((analysis) => (
                <div
                  key={analysis.id}
                  className="flex items-start gap-3 rounded-lg border border-gray-100 p-3 dark:border-gray-700"
                >
                  <Badge
                    variant={
                      outcomeColors[analysis.outcome] ?? outcomeColors.NO_REPLY
                    }
                  >
                    {analysis.outcome}
                  </Badge>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm text-gray-900 dark:text-gray-100 line-clamp-2">
                      {analysis.summary ?? "No summary"}
                    </p>
                    <div className="mt-1 flex flex-wrap gap-3 text-xs text-gray-500 dark:text-gray-400">
                      {analysis.province && <span>{analysis.province}</span>}
                      <span>{analysis.total_messages} messages</span>
                      <span>
                        {new Date(analysis.created_at).toLocaleDateString()}
                      </span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
