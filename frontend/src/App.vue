<script setup lang="ts">
  import { onMounted, ref } from 'vue'

  // interfaces
  interface InferenceImage {
    guid: string
    name: string
    filepath: string
    upload_group_id: string
    uploaded_at?: string
  }

  interface TaskInfo {
    guid: string
    detection_count: number
    task_status: string
  }

  interface Detection {
    id: number
    confidence: number
    x_min: number
    y_min: number
    x_max: number
    y_max: number
  }

  // variables
  const images = ref<InferenceImage[]>([])
  const expandedImages = ref<Record<string, boolean>>({})
  const imageDetails = ref<Record<string, TaskInfo[]>>({})

  // Track active detections and selected task ID per image
  const activeDetections = ref<Record<string, Detection[]>>({})
  const activeTaskId = ref<Record<string, string>>({})

  // Fetch existing uploaded images on mount
  const fetchImages = async () => {
    try {
      const response = await fetch('/images')
      if (response.ok) {
        images.value = await response.json()
      }
    } catch (err) {
      console.error('Failed to fetch images:', err)
    }
  }

  // Start a task for the image guid
  const startTaskOnImage = async (image_guid: string) => {
    try {
      const response = await fetch(`/process-image/${image_guid}`, { method: 'POST' })
      if (!response.ok) {
        throw new Error(`Server returned status ${response.status}`)
      }
    } catch (err) {
      console.error('Failed to start processing on image:', err)
    }
  }

  // Fetch contents for an expanded image
  const toggleExpand = async (img: InferenceImage) => {
    const currentState = !!expandedImages.value[img.guid]
    expandedImages.value[img.guid] = !currentState

    if (!currentState && !imageDetails.value[img.guid]) {
      try {
        const response = await fetch(`/images/${img.guid}/tasks`)
        if (response.ok) {
          const data = await response.json()
          imageDetails.value[img.guid] = data.tasks || []
        } else {
          imageDetails.value[img.guid] = []
        }
      } catch (err) {
        console.error('Failed to fetch tasks for image', err)
        imageDetails.value[img.guid] = []
      }
    }
  }

  // Fetch task details and detections when a task item is clicked
  const selectTaskAndFetchDetections = async (imgGuid: string, task: TaskInfo) => {
    activeTaskId.value[imgGuid] = task.guid
    try {
      const response = await fetch(`/task-details/${task.guid}`)
      if (response.ok) {
        const data = await response.json()
        activeDetections.value[imgGuid] = data.detections || []
      } else {
        activeDetections.value[imgGuid] = []
      }
    } catch (err) {
      console.error('Failed to fetch task detections:', err)
      activeDetections.value[imgGuid] = []
    }
  }

  onMounted(() => {
    fetchImages()
  })
</script>

<template>
  <main class="min-h-screen bg-slate-100 p-8">
    <div class="max-w-3xl mx-auto space-y-8">
      
      <!-- Header -->
      <header class="bg-white p-6 rounded-xl shadow-sm border border-slate-200">
        <h1 class="text-2xl font-bold text-slate-800">Smiley Detection Dashboard</h1>
        <p class="text-sm text-slate-500 mt-1">Upload an image and view associated tasks.</p>
      </header>
      
      <!-- Uploaded Images List -->
      <section class="bg-white p-6 rounded-xl shadow-sm border border-slate-200 space-y-4">
        <h2 class="text-lg font-semibold text-slate-700">Uploaded Images</h2>

        <div v-if="images.length === 0" class="text-sm text-slate-400 italic">
          No images uploaded yet.
        </div>

        <div class="space-y-3">
          <div 
            v-for="img in images" 
            :key="img.guid"
            class="border border-slate-200 rounded-lg p-4 transition hover:border-blue-300 cursor-pointer"
            @click="toggleExpand(img)"
          >
            <!-- Summary Row -->
            <div class="flex justify-between items-center">
              <div>
                <p class="font-medium text-slate-800">{{ img.name }}</p>
                <p class="text-xs text-slate-400 font-mono mt-0.5">Path: {{ img.filepath }}</p>
              </div>
              <span class="text-xs font-semibold text-blue-600 bg-blue-50 px-2.5 py-1 rounded-full">
                {{ expandedImages[img.guid] ? 'Collapse' : 'Expand' }}
              </span>
            </div>

            <!-- Expanded Details -->
            <div v-if="expandedImages[img.guid]" class="mt-4 pt-4 border-t border-slate-100 space-y-3" @click.stop>
              <div class="flex gap-4 items-center">

                <!-- Image Preview & 0 Detections Label -->
                <div class="flex flex-col items-center">
                  <div class="relative inline-block">
                    <img 
                      :src="activeTaskId[img.guid] ? `/tasks/${activeTaskId[img.guid]}/rendered-image` : `/${img.filepath}`" 
                      alt="Preview" 
                      class="w-48 h-auto rounded-lg border border-slate-200 block" 
                    />
                  </div>
                  <!-- Show "0 detections" if a task is selected and detections array is empty -->
                  <div 
                    v-if="activeTaskId[img.guid] && activeDetections[img.guid] && activeDetections[img.guid].length === 0" 
                    class="text-xs text-slate-500 font-medium mt-1.5"
                  >
                    0 detections
                  </div>
                </div>

                <div>
                  <button @click="startTaskOnImage(img.guid)" class="px-3 py-1.5 bg-blue-600 text-white rounded text-xs font-semibold hover:bg-blue-700">
                    Start Task
                  </button>
                </div>
                
                <div>
                  <p class="text-xs text-slate-500"><span class="font-semibold">GUID:</span> {{ img.guid }}</p>
                  <p class="text-xs text-slate-500 mt-1"><span class="font-semibold">Group ID:</span> {{ img.upload_group_id }}</p>
                  <p class="text-xs text-slate-500 mt-1"><span class="font-semibold">Uploaded At:</span> {{ img.uploaded_at ? new Date(img.uploaded_at).toLocaleString() : '--' }}</p>
                </div>
              </div>

              <!-- Associated Tasks List with Status and Count -->
              <div>
                <h4 class="text-xs font-bold uppercase tracking-wider text-slate-500 mb-2">Associated Tasks (Click to View)</h4>
                <div v-if="!imageDetails[img.guid] || imageDetails[img.guid].length === 0" class="text-xs text-slate-400 italic">
                  No tasks associated with this image yet.
                </div>
                <ul v-else class="space-y-1.5">
                  <li 
                    v-for="task in imageDetails[img.guid]" 
                    :key="task.guid" 
                    @click="selectTaskAndFetchDetections(img.guid, task)"
                    :class="[
                      'text-xs font-mono px-3 py-2 rounded cursor-pointer transition flex justify-between items-center',
                      activeTaskId[img.guid] === task.guid ? 'bg-blue-100 text-blue-900 font-bold border border-blue-300' : 'text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200'
                    ]"
                  >
                    <span>{{ task.guid }}</span>
                    <div class="flex gap-2 items-center">
                      <span class="px-1.5 py-0.5 bg-white rounded text-[10px] border border-slate-300 font-sans">
                        Status: {{ task.task_status }}
                      </span>
                      <span class="px-1.5 py-0.5 bg-slate-200 rounded text-[10px] font-sans">
                        Detections: {{ task.detection_count }}
                      </span>
                    </div>
                  </li>
                </ul>
              </div>
            </div>

          </div>
        </div>
      </section>

    </div>
  </main>
</template>