import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from './App.vue'
import './styles.css'
import LoginView from './views/LoginView.vue'
import TeacherHomeView from './views/TeacherHomeView.vue'
import StudentJoinView from './views/StudentJoinView.vue'
import QuestionSetsView from './views/QuestionSetsView.vue'
import QuestionSetDetailView from './views/QuestionSetDetailView.vue'
import SessionCreateView from './views/SessionCreateView.vue'
import TeacherSessionView from './views/TeacherSessionView.vue'
import StudentSessionView from './views/StudentSessionView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/login' },
    { path: '/login', component: LoginView },
    { path: '/teacher', component: TeacherHomeView, meta: { requiresTeacher: true } },
    { path: '/teacher/question-sets', component: QuestionSetsView, meta: { requiresTeacher: true } },
    { path: '/teacher/question-sets/:id', component: QuestionSetDetailView, meta: { requiresTeacher: true } },
    { path: '/teacher/sessions/new', component: SessionCreateView, meta: { requiresTeacher: true } },
    { path: '/teacher/sessions/:id', component: TeacherSessionView, meta: { requiresTeacher: true } },
    { path: '/student/join', component: StudentJoinView },
    { path: '/student/session/:token', component: StudentSessionView },
  ],
})

router.beforeEach((to) => {
  if (to.meta.requiresTeacher && !localStorage.getItem('hhx_access_token')) {
    return '/login'
  }
})

createApp(App).use(router).mount('#app')
