# React + TypeScript Conventions

## Stack
- React 18
- TypeScript 5
- Vite
- React Router 6
- TanStack Query 5
- Tailwind CSS 3
- Lucide React icons

## File Structure
```
frontend/src/
├── App.tsx              # Router setup
├── main.tsx             # Entry point
├── pages/
│   ├── DashboardPage.tsx
│   ├── UniversitiesPage.tsx
│   └── ...
├── components/
│   ├── ui/              # Reusable UI components
│   └── ...
├── hooks/
│   ├── useUniversities.ts
│   └── ...
├── services/
│   └── api.ts           # Axios instance
├── types/
│   └── index.ts
└── utils/
    └── ...
```

## Component Pattern

### Functional Component
```tsx
import { useState, useEffect } from 'react';
import { Button } from '@/components/ui/Button';

interface ComponentProps {
  title: string;
  data: DataType;
  onSave: (data: Data) => void;
}

export function Component({ title, data, onSave }: ComponentProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSave = async () => {
    setIsLoading(true);
    try {
      await onSave(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="p-4 border rounded-lg">
      <h2 className="text-xl font-semibold mb-4">{title}</h2>
      {error && <div className="text-red-600">{error}</div>}
      <Button onClick={handleSave} disabled={isLoading}>
        {isLoading ? 'Saving...' : 'Save'}
      </Button>
    </div>
  );
}
```

### Type Exports
```tsx
// Export types for reuse
export type DataType = {
  id: string;
  name: string;
  createdAt: string;
};

export interface ComponentProps {
  data: DataType;
}
```

## TanStack Query

### Query Hook
```tsx
// hooks/useResource.ts
import { useQuery } from '@tanstack/react-query';
import axios from 'axios';

const API_URL = import.meta.env.VITE_API_URL;

export function useResource(id: string) {
  return useQuery({
    queryKey: ['resource', id],
    queryFn: async () => {
      const { data } = await axios.get(`${API_URL}/api/v1/resource/${id}`);
      return data.data;
    },
    staleTime: 5000,
  });
}
```

### Mutation Hook
```tsx
export function useCreateResource() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (data: CreateData) => {
      const response = await axios.post(`${API_URL}/api/v1/resource`, data);
      return response.data.data;
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['resource'] });
    },
    onError: (error) => {
      console.error('Mutation error:', error);
    },
  });
}
```

### Using Hook in Component
```tsx
export function ResourcePage() {
  const { data, isLoading, error } = useResource('id');
  const createMutation = useCreateResource();

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error: {error.message}</div>;

  return (
    <div>
      <h1>{data?.name}</h1>
      <button onClick={() => createMutation.mutate({...})}>
        Create
      </button>
    </div>
  );
}
```

## React Router

### Route Setup
```tsx
// App.tsx
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { Layout } from './components/Layout';
import { UniversitiesPage } from './pages/UniversitiesPage';
import { DashboardPage } from './pages/DashboardPage';

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<DashboardPage />} />
          <Route path="universities" element={<UniversitiesPage />} />
          <Route path="universities/:id" element={<UniversityDetailPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
```

### Route Params
```tsx
import { useParams } from 'react-router-dom';

export function UniversityDetailPage() {
  const { id } = useParams<{ id: string }>();
  const { data } = useUniversity(id!);

  return <div>{data?.name}</div>;
}
```

## Tailwind CSS

### Common Patterns
```tsx
// Container
<div className="container mx-auto px-4 py-8">

// Card
<div className="bg-white rounded-lg shadow p-6">

// Button
<button className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700">

// Grid
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">

// Flex
<div className="flex items-center justify-between">

// Form
<input
  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-blue-500"
  type="text"
  placeholder="Enter text"
/>
```

### Responsive
```tsx
// Responsive spacing
<div className="px-4 py-2 md:px-6 md:py-4 lg:px-8 lg:py-6">

// Hide on mobile
<div className="hidden md:block">

// Hide on desktop
<div className="md:hidden">
```

## Icons (Lucide React)
```tsx
import { Search, Plus, Trash2, Check } from 'lucide-react';

<Search className="w-5 h-5" />
<Plus className="w-4 h-4 text-green-600" />
<Trash2 className="w-5 h-5 text-red-600 cursor-pointer" />
```

## Form Handling
```tsx
export function Form() {
  const [formData, setFormData] = useState({
    name: '',
    email: '',
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData(prev => ({
      ...prev,
      [e.target.name]: e.target.value,
    }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await createMutation.mutate(formData);
    setFormData({ name: '', email: '' });
  };

  return (
    <form onSubmit={handleSubmit}>
      <input
        name="name"
        value={formData.name}
        onChange={handleChange}
      />
      <button type="submit">Submit</button>
    </form>
  );
}
```

## TypeScript Best Practices

### Avoid `any`
```tsx
// ❌ Bad
function process(data: any) {
  return data.value;
}

// ✅ Good
interface Data {
  value: string;
}

function process(data: Data) {
  return data.value;
}
```

### Type Guards
```tsx
function isString(value: unknown): value is string {
  return typeof value === 'string';
}

if (isString(data)) {
  // TypeScript knows data is string here
}
```

## Error Boundaries
```tsx
// ErrorBoundary.tsx
class ErrorBoundary extends Component<Props, State> {
  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('Error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return <div>Something went wrong</div>;
    }
    return this.props.children;
  }
}
```
