<script lang="ts">
  import { createEventDispatcher } from 'svelte';
  
  const dispatch = createEventDispatcher<{
    select: { script: string };
  }>();
  
  interface Template {
    id: string;
    name: string;
    description: string;
    category: string;
    icon: string;
    script: string;
    requirements?: string[];
    estimatedTime?: string;
  }
  
  const templates: Template[] = [
    {
      id: 'ml-training',
      name: 'ML Training',
      description: 'PyTorch/TensorFlow training template with GPU support',
      category: 'Machine Learning',
      icon: '🧠',
      script: `#!/bin/bash
#SBATCH --job-name=ml-training
#SBATCH --time=04:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8
#SBATCH --gres=gpu:1
#SBATCH --partition=gpu

# Load modules
module load cuda/11.8
module load python/3.10

# Activate environment
source ~/envs/ml/bin/activate

# Training script
python train.py \\
  --data-dir /path/to/data \\
  --output-dir /path/to/output \\
  --epochs 100 \\
  --batch-size 32`,
      requirements: ['GPU', 'CUDA', 'Python'],
      estimatedTime: '4 hours'
    },
    {
      id: 'data-processing',
      name: 'Data Processing',
      description: 'Large-scale data processing with multiprocessing',
      category: 'Data Science',
      icon: '📊',
      script: `#!/bin/bash
#SBATCH --job-name=data-processing
#SBATCH --time=02:00:00
#SBATCH --mem=64G
#SBATCH --cpus-per-task=16
#SBATCH --partition=bigmem

# Load modules
module load python/3.10

# Process data
python process_data.py \\
  --input /path/to/input \\
  --output /path/to/output \\
  --workers 16`,
      requirements: ['High Memory', 'Multi-core'],
      estimatedTime: '2 hours'
    },
    {
      id: 'jupyter-server',
      name: 'Jupyter Server',
      description: 'Interactive Jupyter notebook server',
      category: 'Interactive',
      icon: '📓',
      script: `#!/bin/bash
#SBATCH --job-name=jupyter
#SBATCH --time=08:00:00
#SBATCH --mem=16G
#SBATCH --cpus-per-task=4
#SBATCH --partition=interactive

# Load modules
module load python/3.10

# Get node info
hostname
echo "Jupyter will run on: $(hostname)"

# Start Jupyter
jupyter lab --no-browser --port=8888 --ip=0.0.0.0`,
      requirements: ['Interactive partition'],
      estimatedTime: '8 hours'
    },
    {
      id: 'bioinformatics',
      name: 'Bioinformatics Pipeline',
      description: 'Genomics data analysis pipeline',
      category: 'Bioinformatics',
      icon: '🧬',
      script: `#!/bin/bash
#SBATCH --job-name=bio-pipeline
#SBATCH --time=12:00:00
#SBATCH --mem=128G
#SBATCH --cpus-per-task=32
#SBATCH --partition=bigmem

# Load modules
module load samtools
module load bwa
module load gatk

# Run pipeline
bash pipeline.sh --threads 32`,
      requirements: ['High Memory', 'Bio tools'],
      estimatedTime: '12 hours'
    },
    {
      id: 'mpi-simulation',
      name: 'MPI Simulation',
      description: 'Parallel simulation using MPI',
      category: 'HPC',
      icon: '🔬',
      script: `#!/bin/bash
#SBATCH --job-name=mpi-sim
#SBATCH --time=06:00:00
#SBATCH --ntasks=64
#SBATCH --mem-per-cpu=4G
#SBATCH --partition=compute

# Load MPI
module load openmpi/4.1

# Run simulation
mpirun -n 64 ./simulation`,
      requirements: ['MPI', 'Multi-node'],
      estimatedTime: '6 hours'
    },
    {
      id: 'array-job',
      name: 'Array Job',
      description: 'Process multiple files in parallel',
      category: 'Batch Processing',
      icon: '📁',
      script: `#!/bin/bash
#SBATCH --job-name=array-job
#SBATCH --time=01:00:00
#SBATCH --mem=8G
#SBATCH --cpus-per-task=2
#SBATCH --array=1-100

# Process file based on array index
INPUT_FILE="data/file_\${SLURM_ARRAY_TASK_ID}.txt"
OUTPUT_FILE="output/result_\${SLURM_ARRAY_TASK_ID}.txt"

python process_single.py \\
  --input "\${INPUT_FILE}" \\
  --output "\${OUTPUT_FILE}"`,
      requirements: ['Array support'],
      estimatedTime: '1 hour per task'
    },
    {
      id: 'matlab-compute',
      name: 'MATLAB Computation',
      description: 'Scientific computing with MATLAB',
      category: 'Scientific Computing',
      icon: '📐',
      script: `#!/bin/bash
#SBATCH --job-name=matlab-job
#SBATCH --time=03:00:00
#SBATCH --mem=32G
#SBATCH --cpus-per-task=8

# Load MATLAB
module load matlab/R2023a

# Run MATLAB script
matlab -nodisplay -nosplash -r "run('script.m'); exit"`,
      requirements: ['MATLAB license'],
      estimatedTime: '3 hours'
    },
    {
      id: 'quick-test',
      name: 'Quick Test',
      description: 'Simple test job for debugging',
      category: 'Testing',
      icon: '🧪',
      script: `#!/bin/bash
#SBATCH --job-name=test-job
#SBATCH --time=00:10:00
#SBATCH --mem=1G
#SBATCH --cpus-per-task=1
#SBATCH --partition=debug

echo "Job started on $(hostname)"
echo "Current directory: $(pwd)"
echo "Environment:"
env | sort

# Your test commands here
echo "Test completed successfully"`,
      requirements: ['Debug partition'],
      estimatedTime: '10 minutes'
    }
  ];
  
  let selectedCategory = '';
  let searchTerm = '';
  
  $: categories = [...new Set(templates.map(t => t.category))];
  
  $: filteredTemplates = templates.filter(template => {
    const matchesCategory = !selectedCategory || template.category === selectedCategory;
    const matchesSearch = !searchTerm || 
      template.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      template.description.toLowerCase().includes(searchTerm.toLowerCase()) ||
      template.category.toLowerCase().includes(searchTerm.toLowerCase());
    return matchesCategory && matchesSearch;
  });
  
  function selectTemplate(template: Template) {
    dispatch('select', { script: template.script });
  }
</script>

<div class="template-library">
  <!-- Search & Filter -->
  <div class="library-header">
    <input 
      type="search"
      bind:value={searchTerm}
      placeholder="Search templates..."
      class="search-input"
    />
    
    <div class="category-pills">
      <button 
        class="category-pill"
        class:active={!selectedCategory}
        on:click={() => selectedCategory = ''}
      >
        All
      </button>
      {#each categories as category}
        <button 
          class="category-pill"
          class:active={selectedCategory === category}
          on:click={() => selectedCategory = category}
        >
          {category}
        </button>
      {/each}
    </div>
  </div>
  
  <!-- Template Grid -->
  <div class="template-grid">
    {#each filteredTemplates as template}
      <div 
        class="template-card"
        on:click={() => selectTemplate(template)}
      >
        <div class="template-icon">{template.icon}</div>
        
        <div class="template-content">
          <h3>{template.name}</h3>
          <p class="template-description">{template.description}</p>
          
          <div class="template-meta">
            <span class="meta-badge category">{template.category}</span>
            {#if template.estimatedTime}
              <span class="meta-badge time">
                <svg viewBox="0 0 24 24">
                  <path d="M12,20A8,8 0 0,0 20,12A8,8 0 0,0 12,4A8,8 0 0,0 4,12A8,8 0 0,0 12,20M12,2A10,10 0 0,1 22,12A10,10 0 0,1 12,22C6.47,22 2,17.5 2,12A10,10 0 0,1 12,2M12.5,7V12.25L17,14.92L16.25,16.15L11,13V7H12.5Z" />
                </svg>
                {template.estimatedTime}
              </span>
            {/if}
          </div>
          
          {#if template.requirements && template.requirements.length > 0}
            <div class="requirements">
              <span class="req-label">Requires:</span>
              {#each template.requirements as req}
                <span class="req-chip">{req}</span>
              {/each}
            </div>
          {/if}
        </div>
        
        <div class="template-arrow">
          <svg viewBox="0 0 24 24">
            <path d="M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z" />
          </svg>
        </div>
      </div>
    {/each}
  </div>
</div>

<style>
  .template-library {
    display: flex;
    flex-direction: column;
    height: 100%;
  }
  
  /* Header */
  .library-header {
    padding: 1rem;
    background: #141925;
    border-bottom: 1px solid #2a3142;
    position: sticky;
    top: 0;
    z-index: 10;
  }
  
  .search-input {
    width: 100%;
    padding: 0.75rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 8px;
    color: #e4e8f1;
    font-size: 0.9rem;
    margin-bottom: 0.75rem;
    outline: none;
  }
  
  .search-input:focus {
    border-color: #3b82f6;
  }
  
  .category-pills {
    display: flex;
    gap: 0.5rem;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    padding-bottom: 0.25rem;
  }
  
  .category-pills::-webkit-scrollbar {
    display: none;
  }
  
  .category-pill {
    padding: 0.5rem 0.875rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 20px;
    color: #9ca3af;
    font-size: 0.875rem;
    font-weight: 500;
    white-space: nowrap;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .category-pill.active {
    background: #3b82f6;
    border-color: #3b82f6;
    color: white;
  }
  
  /* Template Grid */
  .template-grid {
    flex: 1;
    overflow-y: auto;
    padding: 1rem;
  }
  
  .template-card {
    display: flex;
    align-items: center;
    gap: 1rem;
    background: #141925;
    border: 1px solid #2a3142;
    border-radius: 12px;
    padding: 1rem;
    margin-bottom: 0.75rem;
    cursor: pointer;
    transition: all 0.2s;
    -webkit-tap-highlight-color: transparent;
  }
  
  .template-card:active {
    background: #1e2433;
    transform: scale(0.98);
  }
  
  .template-icon {
    width: 48px;
    height: 48px;
    background: #1e2433;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 1.5rem;
    flex-shrink: 0;
  }
  
  .template-content {
    flex: 1;
    min-width: 0;
  }
  
  .template-content h3 {
    margin: 0 0 0.25rem 0;
    color: #e4e8f1;
    font-size: 1rem;
    font-weight: 600;
  }
  
  .template-description {
    margin: 0 0 0.5rem 0;
    color: #9ca3af;
    font-size: 0.875rem;
    line-height: 1.4;
  }
  
  .template-meta {
    display: flex;
    gap: 0.5rem;
    margin-bottom: 0.5rem;
  }
  
  .meta-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    padding: 0.25rem 0.5rem;
    background: #1e2433;
    border: 1px solid #2a3142;
    border-radius: 4px;
    color: #9ca3af;
    font-size: 0.75rem;
  }
  
  .meta-badge.category {
    background: rgba(59, 130, 246, 0.1);
    border-color: rgba(59, 130, 246, 0.3);
    color: #3b82f6;
  }
  
  .meta-badge.time svg {
    width: 12px;
    height: 12px;
  }
  
  .requirements {
    display: flex;
    align-items: center;
    gap: 0.25rem;
    flex-wrap: wrap;
  }
  
  .req-label {
    color: #6b7280;
    font-size: 0.7rem;
    text-transform: uppercase;
    font-weight: 600;
  }
  
  .req-chip {
    padding: 0.125rem 0.375rem;
    background: rgba(245, 158, 11, 0.1);
    border: 1px solid rgba(245, 158, 11, 0.2);
    border-radius: 3px;
    color: #f59e0b;
    font-size: 0.7rem;
  }
  
  .template-arrow {
    color: #6b7280;
    flex-shrink: 0;
  }
  
  .template-arrow svg {
    width: 20px;
    height: 20px;
  }
</style>