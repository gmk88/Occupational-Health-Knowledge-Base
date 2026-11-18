import { useEffect, useState } from 'react';
import { listCategories, listTags, type Category, type Tag } from '../../services/documents';

export function SearchFilters({
  selectedCategory,
  onCategory,
  selectedTag,
  onTag,
  selectedBlockType,
  onBlockType,
}: {
  selectedCategory: string;
  onCategory: (value: string) => void;
  selectedTag: string;
  onTag: (value: string) => void;
  selectedBlockType: string;
  onBlockType: (value: string) => void;
}) {
  const [categories, setCategories] = useState<Category[]>([]);
  const [tags, setTags] = useState<Tag[]>([]);

  useEffect(() => {
    const id = window.setTimeout(() => {
      void listCategories().then((response) => setCategories(response.data)).catch(() => {});
      void listTags({ page_size: 100 }).then((response) => setTags(response.data.items)).catch(() => {});
    }, 0);
    return () => window.clearTimeout(id);
  }, []);

  return (
    <div className="filters-panel" aria-label="过滤条件">
      <label className="field"><span>场景</span><select value={selectedCategory} onChange={(event) => onCategory(event.target.value)}>
        <option value="">全部</option>{categories.map((category) => <option key={category.id} value={category.id}>{category.name}</option>)}
      </select></label>
      <label className="field"><span>标签</span><select value={selectedTag} onChange={(event) => onTag(event.target.value)}>
        <option value="">全部</option>{tags.map((tag) => <option key={tag.id} value={tag.id}>{tag.name}</option>)}
      </select></label>
      <label className="field"><span>结果类型</span><select value={selectedBlockType} onChange={(event) => onBlockType(event.target.value)}>
        <option value="">全部</option>
        <option value="text">仅正文</option>
        <option value="table">仅表格</option>
      </select></label>
    </div>
  );
}
