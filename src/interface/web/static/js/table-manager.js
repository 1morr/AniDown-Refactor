/**
 * 可复用的表格管理器
 *
 * 提供表格的渲染、排序、分页、搜索、过滤等完整功能
 */
class TableManager {
  /**
   * 构造函数
   * @param {Object} options - 配置选项
   * @param {string} options.id - 表格唯一标识
   * @param {string} options.apiEndpoint - API端点URL
   * @param {Array} options.columns - 列配置数组
   * @param {string} options.initialSort - 初始排序列
   * @param {string} options.initialOrder - 初始排序方向 ('asc' or 'desc')
   * @param {number} options.perPage - 每页显示数量
   * @param {Function} options.rowRenderer - 自定义行渲染函数
   * @param {Function} options.onDataLoaded - 数据加载完成回调
   */
  constructor(options) {
    this.id = options.id;
    this.apiEndpoint = options.apiEndpoint;
    this.currentPage = 1;
    this.perPage = options.perPage || 20;
    this.searchTerm = '';
    this.sortColumn = options.initialSort || 'created_at';
    this.sortOrder = options.initialOrder || 'desc';
    this.filters = {};
    this.columns = options.columns || [];
    this.rowRenderer = options.rowRenderer; // 自定义行渲染函数
    this.onDataLoaded = options.onDataLoaded; // 数据加载回调
    this.isLoading = false;
    this.lastData = null; // 缓存最后一次的数据
  }

  /**
   * 渲染表格
   * @param {boolean} showLoading - 是否显示加载状态
   */
  async render(showLoading = true) {
    if (this.isLoading) return;

    try {
      this.isLoading = true;

      if (showLoading) {
        this.showLoading();
      }

      const params = new URLSearchParams({
        page: this.currentPage,
        per_page: this.perPage,
        search: this.searchTerm,
        sort_column: this.sortColumn,
        sort_order: this.sortOrder,
        ...this.filters
      });

      const response = await fetch(`${this.apiEndpoint}?${params}`);
      const data = await response.json();

      if (data.error) {
        showFlashMessage('error', data.error);
        this.showError(data.error);
        return;
      }

      this.lastData = data;

      // 渲染表格内容
      this.renderTableBody(data.data || data.anime_list || data.downloads || []);

      // 渲染分页
      this.renderPagination(data.pagination || data);

      // 更新排序指示器
      this.updateSortIndicators();

      // 调用回调函数
      if (this.onDataLoaded) {
        this.onDataLoaded(data);
      }

    } catch (error) {
      console.error('加载数据失败:', error);
      showFlashMessage('error', '加载数据失败: ' + error.message);
      this.showError('加载数据失败');
    } finally {
      this.isLoading = false;
    }
  }

  /**
   * 渲染表格主体
   * @param {Array} rows - 数据行数组
   */
  renderTableBody(rows) {
    const tbody = document.getElementById(`${this.id}-body`);
    if (!tbody) return;

    if (rows.length === 0) {
      tbody.innerHTML = `
        <tr>
          <td colspan="${this.columns.length}" class="text-center py-12">
            <div class="text-slate-400 dark:text-gray-500">
              <i class="fas fa-inbox text-4xl mb-3"></i>
              <p class="text-sm">暂无数据</p>
            </div>
          </td>
        </tr>
      `;
      return;
    }

    // 使用自定义渲染器或默认渲染器
    const html = rows.map(row => {
      if (this.rowRenderer) {
        return this.rowRenderer(row, this.columns);
      }
      return this.defaultRowRenderer(row);
    }).join('');

    tbody.innerHTML = html;
  }

  /**
   * 默认行渲染器
   * @param {Object} row - 数据行
   * @returns {string} HTML字符串
   */
  defaultRowRenderer(row) {
    let html = '<tr class="hover:bg-slate-50 dark:hover:bg-white/5 transition-colors">';

    this.columns.forEach(col => {
      const value = row[col.key];
      const align = col.align || 'left';
      const displayValue = this.formatCellValue(value, col);
      html += `<td class="py-3 px-2 text-${align}">${displayValue}</td>`;
    });

    html += '</tr>';
    return html;
  }

  /**
   * 格式化单元格值
   * @param {any} value - 原始值
   * @param {Object} col - 列配置
   * @returns {string} 格式化后的值
   */
  formatCellValue(value, col) {
    if (value === null || value === undefined) return '-';

    // 如果有自定义格式化函数
    if (col.formatter) {
      return col.formatter(value);
    }

    // 根据列类型自动格式化
    switch (col.type) {
      case 'date':
        return formatDate(value, 'date');
      case 'datetime':
        return formatDate(value, 'datetime');
      case 'time':
        return formatDate(value, 'time');
      case 'relative-time':
        return formatRelativeTime(new Date(value));
      case 'filesize':
        return formatFileSize(value);
      case 'percentage':
        return formatPercentage(value);
      case 'boolean':
        return value ? '是' : '否';
      default:
        return escapeHtml(String(value));
    }
  }

  /**
   * 渲染分页控件
   * @param {Object} paginationData - 分页数据
   */
  renderPagination(paginationData) {
    const total = paginationData.total_count || paginationData.total || 0;
    const currentPage = paginationData.current_page || this.currentPage;
    const perPage = paginationData.per_page || this.perPage;
    const totalPages = paginationData.total_pages || Math.ceil(total / perPage);

    // 更新计数显示
    const start = total > 0 ? (currentPage - 1) * perPage + 1 : 0;
    const end = Math.min(currentPage * perPage, total);

    const startElem = document.getElementById(`${this.id}-page-start`);
    const endElem = document.getElementById(`${this.id}-page-end`);
    const totalElem = document.getElementById(`${this.id}-total`);

    if (startElem) startElem.textContent = start;
    if (endElem) endElem.textContent = end;
    if (totalElem) totalElem.textContent = total;

    // 渲染分页按钮
    const paginationContainer = document.getElementById(`${this.id}-pagination`);
    if (!paginationContainer) return;

    let html = '';

    // 上一页按钮
    if (currentPage > 1) {
      html += `<button onclick="table_${this.id}.changePage(${currentPage - 1})"
                       class="px-2 py-1 rounded hover:bg-slate-200 dark:hover:bg-white/10
                              text-slate-600 dark:text-slate-400 transition-colors">
                 <i class="fas fa-chevron-left text-xs"></i>
               </button>`;
    } else {
      html += `<button disabled
                       class="px-2 py-1 rounded text-slate-300 dark:text-gray-600 cursor-not-allowed">
                 <i class="fas fa-chevron-left text-xs"></i>
               </button>`;
    }

    // 页码按钮
    const maxButtons = 7; // 最多显示7个页码按钮
    let startPage = Math.max(1, currentPage - Math.floor(maxButtons / 2));
    let endPage = Math.min(totalPages, startPage + maxButtons - 1);

    // 调整起始页
    if (endPage - startPage < maxButtons - 1) {
      startPage = Math.max(1, endPage - maxButtons + 1);
    }

    // 第一页
    if (startPage > 1) {
      html += `<button onclick="table_${this.id}.changePage(1)"
                       class="px-2.5 py-1 rounded hover:bg-slate-200 dark:hover:bg-white/10
                              text-slate-600 dark:text-slate-400 text-xs transition-colors">
                 1
               </button>`;
      if (startPage > 2) {
        html += `<span class="px-2 text-slate-400 dark:text-gray-600 text-xs">...</span>`;
      }
    }

    // 中间页码
    for (let i = startPage; i <= endPage; i++) {
      if (i === currentPage) {
        html += `<button class="px-2.5 py-1 rounded bg-purple-600 text-white text-xs font-bold">
                   ${i}
                 </button>`;
      } else {
        html += `<button onclick="table_${this.id}.changePage(${i})"
                         class="px-2.5 py-1 rounded hover:bg-slate-200 dark:hover:bg-white/10
                                text-slate-600 dark:text-slate-400 text-xs transition-colors">
                   ${i}
                 </button>`;
      }
    }

    // 最后一页
    if (endPage < totalPages) {
      if (endPage < totalPages - 1) {
        html += `<span class="px-2 text-slate-400 dark:text-gray-600 text-xs">...</span>`;
      }
      html += `<button onclick="table_${this.id}.changePage(${totalPages})"
                       class="px-2.5 py-1 rounded hover:bg-slate-200 dark:hover:bg-white/10
                              text-slate-600 dark:text-slate-400 text-xs transition-colors">
                 ${totalPages}
               </button>`;
    }

    // 下一页按钮
    if (currentPage < totalPages) {
      html += `<button onclick="table_${this.id}.changePage(${currentPage + 1})"
                       class="px-2 py-1 rounded hover:bg-slate-200 dark:hover:bg-white/10
                              text-slate-600 dark:text-slate-400 transition-colors">
                 <i class="fas fa-chevron-right text-xs"></i>
               </button>`;
    } else {
      html += `<button disabled
                       class="px-2 py-1 rounded text-slate-300 dark:text-gray-600 cursor-not-allowed">
                 <i class="fas fa-chevron-right text-xs"></i>
               </button>`;
    }

    paginationContainer.innerHTML = html;
  }

  /**
   * 切换排序
   * @param {string} column - 列名
   */
  toggleSort(column) {
    if (this.sortColumn === column) {
      this.sortOrder = this.sortOrder === 'asc' ? 'desc' : 'asc';
    } else {
      this.sortColumn = column;
      this.sortOrder = 'desc';
    }
    this.currentPage = 1;
    this.render();
  }

  /**
   * 更新排序指示器
   */
  updateSortIndicators() {
    // 重置所有指示器
    document.querySelectorAll('.sort-indicator').forEach(indicator => {
      indicator.className = 'sort-indicator';
      indicator.innerHTML = '<i class="fas fa-sort text-xs opacity-30"></i>';
    });

    // 设置当前排序列的指示器
    const currentIndicator = document.getElementById(`sort-${this.sortColumn}`);
    if (currentIndicator) {
      currentIndicator.classList.add('active');
      currentIndicator.innerHTML = this.sortOrder === 'asc'
        ? '<i class="fas fa-sort-up text-xs"></i>'
        : '<i class="fas fa-sort-down text-xs"></i>';
    }
  }

  /**
   * 切换到指定页
   * @param {number} page - 页码
   */
  changePage(page) {
    this.currentPage = page;
    this.render();
    scrollToTop(true);
  }

  /**
   * 设置过滤器
   * @param {string} key - 过滤器键名
   * @param {any} value - 过滤器值
   */
  setFilter(key, value) {
    this.filters[key] = value;
    this.currentPage = 1;
    this.render();
  }

  /**
   * 移除过滤器
   * @param {string} key - 过滤器键名
   */
  removeFilter(key) {
    delete this.filters[key];
    this.currentPage = 1;
    this.render();
  }

  /**
   * 清除所有过滤器
   */
  clearFilters() {
    this.filters = {};
    this.currentPage = 1;
    this.render();
  }

  /**
   * 设置搜索词
   * @param {string} term - 搜索词
   */
  setSearch(term) {
    this.searchTerm = term;
    this.currentPage = 1;
    this.render();
  }

  /**
   * 设置每页显示数量
   * @param {number} perPage - 每页数量
   */
  setPerPage(perPage) {
    this.perPage = perPage;
    this.currentPage = 1;
    this.render();
  }

  /**
   * 刷新当前页
   */
  refresh() {
    this.render();
  }

  /**
   * 显示加载状态
   */
  showLoading() {
    const tbody = document.getElementById(`${this.id}-body`);
    if (!tbody) return;

    tbody.innerHTML = `
      <tr>
        <td colspan="${this.columns.length}" class="text-center py-12">
          <div class="inline-flex items-center gap-3 text-slate-400 dark:text-gray-500">
            <i class="fas fa-spinner fa-spin text-2xl"></i>
            <span class="text-sm">加载中...</span>
          </div>
        </td>
      </tr>
    `;
  }

  /**
   * 显示错误状态
   * @param {string} message - 错误消息
   */
  showError(message) {
    const tbody = document.getElementById(`${this.id}-body`);
    if (!tbody) return;

    tbody.innerHTML = `
      <tr>
        <td colspan="${this.columns.length}" class="text-center py-12">
          <div class="text-red-500">
            <i class="fas fa-exclamation-circle text-4xl mb-3"></i>
            <p class="text-sm">${escapeHtml(message)}</p>
            <button onclick="table_${this.id}.refresh()"
                    class="mt-3 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 text-sm">
              重试
            </button>
          </div>
        </td>
      </tr>
    `;
  }

  /**
   * 获取选中的行
   * @returns {Array} 选中行的数据数组
   */
  getSelectedRows() {
    const checkboxes = document.querySelectorAll(`#${this.id}-body input[type="checkbox"]:checked`);
    return Array.from(checkboxes).map(cb => JSON.parse(cb.dataset.row || '{}'));
  }

  /**
   * 导出数据为CSV
   * @param {string} filename - 文件名
   */
  exportToCSV(filename = 'export.csv') {
    if (!this.lastData || !this.lastData.data) {
      showFlashMessage('warning', '没有可导出的数据');
      return;
    }

    const data = this.lastData.data;
    const headers = this.columns.map(col => col.label);
    const rows = data.map(row =>
      this.columns.map(col => row[col.key] || '')
    );

    const csvContent = [
      headers.join(','),
      ...rows.map(row => row.map(cell => `"${cell}"`).join(','))
    ].join('\n');

    const blob = new Blob(['\ufeff' + csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();

    showFlashMessage('success', '导出成功');
  }
}

// 导出到全局
window.TableManager = TableManager;

console.log('✅ TableManager 表格管理器已加载');
